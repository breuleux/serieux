"""
Command-line argument parser built on GroupState (third attempt).

For each token we scan the current state to find eligible fields, picking the
rightmost one that matches. This lets sequences and union branches work naturally
as state evolves via GroupState.advance().
"""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from typing import Any

from ...features.tagset import tag_field
from ...linearize import GroupState, LinearField, LinearState
from .errors import ParseError
from .tokenize import Loc, LongOpt, Separator, ShortOpt, Value


########
# Misc #
########


class Word:
    def __init__(self, word: str):
        self.value = word


@dataclass(kw_only=True)
class Control:
    # [alias: -h]
    # Show this help message and exit
    help: bool = False

    def build(self, parser, vals):
        from .help import format_help

        if self.help:
            print(format_help(parser.gs, parser.prog, parser.root_type, color=sys.stdout.isatty()))
            sys.exit(0)

        if parser.errors:
            raise ParseError._from_items(parser.errors)

        return vals


#################
# Option naming #
#################


def _option_strings(fld: LinearField) -> tuple[list[str], list[str]]:
    """Return ``(primary_names, alias_names)`` without leading ``--``.

    Primary names are ``[long, short]`` (e.g. ``['abc.def', 'def']``) or just
    ``[long]`` when both are identical.  Aliases come from field metadata.

    For ``$class`` discriminator fields the parent field's identifier/name is
    used so the option appears as e.g. ``--animal`` rather than ``--animal.$class``.

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
    if sn is None or (
        sn == tag_field and fld.parent is not None and fld.parent.field.serialized_name is None
    ):
        # Derive option name from nearest named ancestor
        anc = _effective_parent(fld) if sn is None else _effective_parent(fld.parent)
        if anc is None:
            return [], []
        long = _cli_name(anc.identifier)
        short = _cli_name(anc.field.serialized_name)
        primary = [long] if (not long or long == short) else [long, short]
        aliases = fld.field.metadata.get("alias", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        return primary, [a.lstrip("-") for a in aliases]

    f = fld.field
    if f.serialized_name == tag_field and fld.parent is not None:
        eff = fld.parent.identifier
        short_sn = fld.parent.field.serialized_name
    else:
        eff = fld.identifier
        short_sn = f.serialized_name

    if opt := f.metadata.get("option"):
        primary = [opt.lstrip("-")]
    else:
        long = _cli_name(eff)
        short = _cli_name(short_sn)
        primary = [long] if (not short or long == short) else [long, short]

    aliases = f.metadata.get("alias", [])
    if isinstance(aliases, str):
        aliases = [aliases]
    aliases = [a.lstrip("-") for a in aliases]

    return primary, aliases


###########
# Helpers #
###########


def _cli_name(s: str) -> str:
    parts = [p for p in s.split(".") if not p.startswith("__")]
    return ".".join(parts).replace("_", "-")


def _eligible(gs: GroupState, fld: LinearField) -> bool:
    """Return True if fld can be advanced (AVAILABLE or ADVANCE state)."""
    fs = gs.state.get(fld)
    return fs is not None and fs.state in (LinearState.AVAILABLE, LinearState.ADVANCE)


def _named_candidates(gs: GroupState, name: str) -> list[LinearField]:
    """All eligible non-positional fields whose option strings include *name*.

    Returned in state-dict order; the rightmost eligible match is last.
    """
    result = []
    for fld in gs.state:
        if not _eligible(gs, fld) or fld.positional:
            continue
        primary, aliases = _option_strings(fld)
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


def _format_trigger(fld: LinearField) -> str:
    """Format a single trigger field as a human-readable prerequisite."""
    if fld.positional:
        if fld.expected_value is not None:
            return repr(fld.expected_value)
        return fld.field.serialized_name.upper() if fld.field.serialized_name else "ARG"
    primary, _ = _option_strings(fld)
    opt = f"--{primary[0]}" if primary else fld.identifier
    if fld.expected_value is not None:
        return f"{opt}={fld.expected_value!r}"
    return opt


def _explain_unknown_named(gs: GroupState, name: str) -> str | None:
    """If *name* matches a LATENT or UNAVAILABLE field, return an explanation string."""
    latent_hints = []
    unavailable_hints = []

    for fld in gs.state:
        fs = gs.state[fld]
        if fld.positional:
            continue
        try:
            primary, aliases = _option_strings(fld)
        except Exception:
            continue
        if name not in primary + aliases:
            continue

        if fs.state == LinearState.LATENT:
            triggers = gs.latent_triggers(fld)
            if triggers:
                prereqs = " or ".join(_format_trigger(t) for t in triggers)
                latent_hints.append(f"--{name} requires {prereqs}")
            else:
                latent_hints.append(f"--{name} is not yet available")
        elif fs.state == LinearState.UNAVAILABLE:
            disabler = gs.disabled_by(fld)
            if disabler is not None:
                latent_hints.append(f"--{name} was disabled by {_format_trigger(disabler)}")
            else:
                unavailable_hints.append(f"--{name} is not available")

    hints = latent_hints + unavailable_hints
    return hints[0] if hints else None


##########
# Parser #
##########


class CliParser:
    def __init__(
        self,
        gs: GroupState,
        prog: str | None = None,
        argv: list[str] | None = None,
        deserialize=None,
        root_type: type | None = None,
    ) -> None:
        self.gs = gs
        self.prog = prog
        self.argv = argv or []
        self.result: dict[str, Any] = {}
        self.errors: list[tuple[str, Loc | None]] = []
        self.deserialize = deserialize
        self.root_type = root_type

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
        self.result[concrete_id] = self.deserialize(fld.type, Word(value))

    def _consume_value(
        self, key_loc: Loc, queue: deque, name: str | None = None
    ) -> tuple[str, Loc] | None:
        if not queue or not isinstance(queue[0], Value):
            msg = f"Missing value for argument '{name}'" if name else "Expected a value"
            self.errors.append((msg, key_loc))
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
            hint = _explain_unknown_named(self.gs, name)
            msg = hint if hint else f"Unknown option: --{name}"
            self.errors.append((msg, self._ploc(tok.name_loc)))
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
            res = self._consume_value(self._ploc(tok.name_loc), queue, name=name)
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
                hint = _explain_unknown_named(self.gs, ch)
                msg = hint if hint else f"Unknown option: -{ch}"
                self.errors.append((msg, full_loc))
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
                res = self._consume_value(char_loc, queue, name=ch)
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
        # For positionals, prefer leftmost (declaration order); specific expected_value first.
        fld = None
        if candidates:
            specific = [f for f in candidates if f.expected_value == tok.text]
            generic = [f for f in candidates if f.expected_value is None]
            fld = (specific or generic or candidates)[0]
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

        return self.result
