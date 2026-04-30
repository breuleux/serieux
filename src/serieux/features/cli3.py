"""
Command-line argument parser built on GroupState (third attempt).

For each token we scan the current state to find eligible fields, picking the
rightmost one that matches. This lets sequences and union branches work naturally
as state evolves via GroupState.advance().
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from collections import deque
from typing import Any

from ovld import Medley, ovld, recurse

from serieux.ctx import Context

from .cli2 import (
    Loc,
    LongOpt,
    ParseError,
    Separator,
    ShortOpt,
    Value,
    _cli_name,
    _option_strings,
    tokenize,
)
from .dotted import unflatten
from .linearize import GroupState, LinearField, LinearState, linearize
from .tagset import tag_field

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _coerce(tp: type, value: str) -> Any:
    """Convert a CLI string to a Python primitive type when possible."""
    if not isinstance(value, str):
        return value
    try:
        if tp is int:
            return int(value)
        if tp is float:
            return float(value)
    except (ValueError, TypeError):
        pass
    return value


def _eligible(gs: GroupState, fld: LinearField) -> bool:
    """Return True if fld can be advanced (AVAILABLE or ADVANCE state)."""
    fs = gs.state.get(fld)
    return fs is not None and fs.state in (LinearState.AVAILABLE, LinearState.ADVANCE)


def _field_option_strings(fld: LinearField) -> tuple[list[str], list[str]]:
    """Like cli2's _option_strings but handles sequence element fields (serialized_name=None).

    For sequence elements the option name is derived from the nearest named ancestor.
    """
    # Walk up to find the nearest ancestor with a real serialized_name.
    # This handles both bare list elements (serialized_name=None) and
    # $class fields whose parent is a list element.
    def _effective_parent(lf: LinearField) -> LinearField | None:
        p = lf.parent
        while p is not None and p.field.serialized_name is None:
            p = p.parent
        return p

    sn = fld.field.serialized_name
    if sn is None or (sn == tag_field and fld.parent is not None and fld.parent.field.serialized_name is None):
        # Derive option name from nearest named ancestor
        anc = _effective_parent(fld) if sn is None else _effective_parent(fld.parent)
        if anc is None:
            return [], []
        long = _cli_name(anc.identifier)
        short = _cli_name(anc.field.serialized_name)
        primary = [long] if long == short else [long, short]
        aliases = fld.field.metadata.get("alias", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        return primary, [a.lstrip("-") for a in aliases]
    return _option_strings(fld)


def _named_candidates(gs: GroupState, name: str) -> list[LinearField]:
    """All eligible non-positional fields whose option strings include *name*.

    Returned in state-dict order; the rightmost eligible match is last.
    """
    result = []
    for fld in gs.state:
        if not _eligible(gs, fld) or fld.positional:
            continue
        primary, aliases = _field_option_strings(fld)
        if name in primary + aliases:
            result.append(fld)
    return result


def _positional_candidates(gs: GroupState) -> list[LinearField]:
    """All eligible positional fields, in state-dict order (leftmost = first)."""
    return [fld for fld in gs.state if _eligible(gs, fld) and fld.positional]


def _pick(candidates: list[LinearField], value: str | None = None) -> LinearField | None:
    """Pick the rightmost candidate (for named options).

    When *value* is known, prefer fields whose ``expected_value`` matches it;
    fall back to fields with no ``expected_value`` constraint; finally take
    the rightmost candidate regardless.
    """
    if not candidates:
        return None
    if value is not None:
        specific = [
            f for f in candidates if f.expected_value is not None and f.expected_value == value
        ]
        if specific:
            return specific[-1]
    generic = [f for f in candidates if f.expected_value is None]
    return (generic or candidates)[-1]


def _needs_value(fld: LinearField) -> bool:
    """Return True if the field must consume a value token (i.e. not a bool flag)."""
    return fld.type is not bool


# ═══════════════════════════════════════════════════════════════════════════════
# Parser
# ═══════════════════════════════════════════════════════════════════════════════


class Cli3Parser:
    def __init__(
        self,
        gs: GroupState,
        prog: str | None = None,
        argv: list[str] | None = None,
    ) -> None:
        self.gs = gs
        self.prog = prog
        self.argv = argv or []
        self.result: dict[str, Any] = {}
        self.errors: list[tuple[str, Loc | None]] = []

    def _ploc(self, loc: Loc) -> Loc:
        if self.prog and loc.prog != self.prog:
            from dataclasses import replace

            return replace(loc, prog=self.prog)
        return loc

    def _advance(self, fld: LinearField, value: Any, loc: Loc) -> None:
        concrete_id = self.gs.advance(fld)
        if concrete_id is False:
            self.errors.append((f"Cannot assign field {fld.identifier!r}", loc))
            return
        self.result[concrete_id] = _coerce(fld.type, value)

    def _consume_value(self, key_loc: Loc, queue: deque) -> tuple[str, Loc] | None:
        if not queue or not isinstance(queue[0], Value):
            self.errors.append(("Expected a value", key_loc))
            return None
        tok = queue.popleft()
        return tok.text, self._ploc(tok.loc)

    # ── Token handlers ─────────────────────────────────────────────────────────

    def _handle_long(self, tok: LongOpt, queue: deque) -> None:
        name = tok.name
        candidates = _named_candidates(self.gs, name)

        if not candidates:
            # Support --no-X negation for plain bool fields
            if name.startswith("no-"):
                neg_cands = _named_candidates(self.gs, name[3:])
                plain_bool = [f for f in neg_cands if not _needs_value(f) and not f.unlock]
                if plain_bool:
                    fld = plain_bool[-1]
                    if tok.value is not None:
                        self.errors.append(
                            (
                                f"--{name} is a flag and does not take a value",
                                self._ploc(tok.value_loc),
                            )
                        )
                        return
                    concrete_id = self.gs.advance(fld)
                    if concrete_id is not False:
                        self.result[concrete_id] = False
                    return
            self.errors.append((f"Unknown option: --{name}", self._ploc(tok.name_loc)))
            # Speculatively skip the next Value — likely this option's argument.
            if tok.value is None and queue and isinstance(queue[0], Value):
                queue.popleft()
            return

        # All bool flags?
        if all(not _needs_value(f) for f in candidates):
            if tok.value is not None:
                self.errors.append(
                    (f"--{name} is a flag and does not take a value", self._ploc(tok.value_loc))
                )
                return
            fld = _pick(candidates)
            concrete_id = self.gs.advance(fld)
            if concrete_id is not False:
                self.result[concrete_id] = True
            return

        # Needs a value
        if tok.value is not None:
            value, value_loc = tok.value, self._ploc(tok.value_loc)
        else:
            res = self._consume_value(self._ploc(tok.name_loc), queue)
            if res is None:
                return
            value, value_loc = res

        fld = _pick(candidates, value)
        if fld is None:
            self.errors.append((f"No matching option for --{name}={value!r}", value_loc))
            return
        self._advance(fld, value, value_loc)

    def _handle_short(self, tok: ShortOpt, queue: deque) -> None:
        chars = tok.chars
        argv = tok.chars_loc.argv
        idx = tok.chars_loc.arg_index
        base = tok.chars_loc.start

        i = 0
        while i < len(chars):
            ch = chars[i]
            char_loc = self._ploc(Loc(argv, idx, base + i, base + i + 1))
            candidates = _named_candidates(self.gs, ch)

            if not candidates:
                full_loc = self._ploc(Loc(argv, idx, 0 if i == 0 else base + i, base + i + 1))
                self.errors.append((f"Unknown option: -{ch}", full_loc))
                i += 1
                continue

            if all(not _needs_value(f) for f in candidates):
                fld = _pick(candidates)
                concrete_id = self.gs.advance(fld)
                if concrete_id is not False:
                    self.result[concrete_id] = True
                i += 1
                continue

            # Needs a value: rest of chars cluster, then inline =val, then next token
            rest = chars[i + 1 :]
            if rest:
                rest_loc = self._ploc(Loc(argv, idx, base + i + 1, tok.chars_loc.end))
                value, value_loc = rest, rest_loc
            elif tok.value is not None:
                value, value_loc = tok.value, self._ploc(tok.value_loc)
            else:
                res = self._consume_value(char_loc, queue)
                if res is None:
                    break
                value, value_loc = res

            fld = _pick(candidates, value)
            if fld is None:
                self.errors.append((f"Unknown option: -{ch}", char_loc))
                break
            self._advance(fld, value, value_loc)
            break  # value consumed — remaining chars were the value

    def _handle_positional(self, tok: Value) -> None:
        candidates = _positional_candidates(self.gs)
        fld = _pick(candidates, tok.text)
        if fld is None:
            self.errors.append(
                (f"Unexpected positional argument: {tok.text!r}", self._ploc(tok.loc))
            )
            return
        self._advance(fld, tok.text, self._ploc(tok.loc))

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self, tokens: list) -> dict[str, Any]:
        queue: deque = deque(tokens)
        while queue:
            tok = queue.popleft()
            if isinstance(tok, Separator):
                continue
            elif isinstance(tok, LongOpt):
                self._handle_long(tok, queue)
            elif isinstance(tok, ShortOpt):
                self._handle_short(tok, queue)
            else:
                self._handle_positional(tok)

        if self.errors:
            raise ParseError._from_items(self.errors)

        return self.result


# ═══════════════════════════════════════════════════════════════════════════════
# Public interface
# ═══════════════════════════════════════════════════════════════════════════════


def parse(
    root_type: type,
    argv: list[str] | None = None,
    prog: str | None = None,
) -> dict:
    """Parse *argv* (defaults to ``sys.argv[1:]``) against *root_type*'s linearized schema."""
    if argv is None:
        argv = sys.argv[1:]
    if prog is None:
        prog = sys.argv[0]

    tokens = tokenize(argv)
    root_group = linearize(root_type)
    gs = GroupState(root_group)
    parser = Cli3Parser(gs, prog=prog, argv=argv)
    result = parser.run(tokens)
    return unflatten(result, allow_lists=True)


@dataclass
class CommandLineArguments:
    """Wrapper around an argv list, consumed by :class:`FromArguments`."""

    arguments: list[str]


class FromArguments(Medley):
    """Serieux Medley that allows deserializing any type directly from CLI args."""

    @ovld(priority=1)
    def deserialize(self, t: Any, obj: CommandLineArguments, ctx: Context):
        vals = parse(t, obj.arguments)
        try:
            return recurse(t, vals, ctx)
        except ParseError:
            raise
        except Exception as exc:
            # Try to attach a source location from spans
            try:
                from ..exc import find_information

                info = find_information(exc=exc, ctx=ctx)
                path = ".".join(str(p) for p in info.path)
                if loc := vals.spans.get(path):
                    raise ParseError(str(exc), loc) from None
            except Exception:
                pass
            raise
