"""
Command-line argument parser built on GroupState (third attempt).

For each token we scan the current state to find eligible fields, picking the
rightmost one that matches. This lets sequences and union branches work naturally
as state evolves via GroupState.advance().
"""

from __future__ import annotations

import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import cache, cached_property
from typing import Any

from ovld import ovld

from ...features.tagset import tag_field
from ...linearize import GroupState, LinearField
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
            print(format_help(parser, parser.root_type, color=sys.stdout.isatty()))
            sys.exit(0)

        if parser.errors:
            raise ParseError._from_items(parser.errors)

        return vals


#################
# Option naming #
#################


def _cli_name(s: str) -> str:
    parts = [p for p in s.split(".") if not p.startswith("__")]
    return ".".join(parts).replace("_", "-")


def dashify(name: str) -> str:
    return f"-{name}" if len(name) == 1 else f"--{name}"


@dataclass
class Option:
    key: str
    field: LinearField

    def needs_value(self) -> bool:
        """Return True if the field must consume a value token (i.e. not a bool flag)."""
        return self.field.type is not bool

    def specificity(self, value) -> int:
        if self.field.expected_value:
            return 2 if value == self.field.expected_value else 0
        else:
            return 1

    @property
    def unlock(self):
        return self.field.unlock


def _options(fld: LinearField) -> list[str]:
    """Return ``(primary_names, alias_names)`` with leading dashes.

    Primary names are ``[long, short]`` (e.g. ``['--abc.def', '--def']``) or just
    ``[long]`` when both are identical.  Aliases come from field metadata.

    For ``$class`` discriminator fields the parent field's identifier/name is
    used so the option appears as e.g. ``--animal`` rather than ``--animal.$class``.

    For sequence elements the option name is derived from the nearest named ancestor.
    """

    # Walk up to find the nearest ancestor with a real serialized_name.
    # This handles both bare list elements (serialized_name=None) and
    # $class fields whose parent is a list element.
    def _effective_field(lf: LinearField) -> LinearField | None:
        p = lf
        while p.field.serialized_name is None or p.field.serialized_name == tag_field:
            p = p.parent
        return p

    eff = _effective_field(fld)
    meta = eff.field.metadata

    if opt := meta.get("option"):
        long = short = opt.lstrip("-")
    else:
        long = _cli_name(eff.identifier)
        short = _cli_name(eff.field.serialized_name)

    primary = [dashify(long)] if (not short or long == short) else [dashify(long), dashify(short)]
    aliases = meta.get("alias", [])
    if isinstance(aliases, str):
        aliases = [aliases]
    aliases = [dashify(a.lstrip("-")) for a in aliases]

    names = primary + aliases
    return [Option(name, fld) for name in names]


###########
# Helpers #
###########


def _pick(candidates: list[Option], value: str | None = None) -> Option | None:
    """Pick the rightmost candidate (for named options).

    When *value* is known, prefer fields whose ``expected_value`` matches it;
    fall back to fields with no ``expected_value`` constraint; finally take
    the rightmost candidate regardless.
    """
    candidates = [
        (spc, c) for c in candidates if (spc := (c.specificity(value) if value is not None else 1))
    ]
    candidates.sort(key=lambda c: c[0])
    return candidates[-1][1] if candidates else None


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
        self.option_map = defaultdict(list)
        self.populate_options()

    def _ploc(self, loc: Loc) -> Loc:
        if self.prog and loc.prog != self.prog:
            from dataclasses import replace

            return replace(loc, prog=self.prog)
        return loc

    def _advance(self, opt: Option, value: Any, loc: Loc) -> None:
        fld = opt.field
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

    @cached_property
    def formatter(self):
        from .fmt import ArgparseFormatter

        return ArgparseFormatter(self)

    # ── Options names ─────────────────────────────────────────────────────────-

    def populate_options(self):
        for fld in self.gs.state:
            if fld.positional:
                opts = [Option("*", fld)]
            else:
                opts = _options(fld)
            for opt in opts:
                self.option_map[opt.key].append(opt)

    @cache
    def option_strings(self, fld: LinearField):
        return [opt.key for opt in _options(fld)]

    def candidates(self, key: str) -> list[LinearField]:
        """All eligible fields, key being an option or '*' if positional.

        Returned in state-dict order; the rightmost eligible match is last.
        """
        return [opt for opt in self.option_map[key] if self.gs.eligible(opt.field)]

    # ── Token handlers ─────────────────────────────────────────────────────────

    @ovld
    def _handle(self, tok: LongOpt, queue: deque) -> None:
        opt = tok.name
        candidates = self.candidates(opt)

        if not candidates:
            # Support --no-X negation for plain bool fields
            if opt.startswith("--no-"):
                neg_cands = self.candidates(dashify(opt[5:]))
                plain_bool = [o for o in neg_cands if not o.needs_value() and not o.unlock]
                if plain_bool:
                    fld = plain_bool[-1].field
                    if tok.value is not None:
                        self.errors.append(
                            (
                                f"{opt} is a flag and does not take a value",
                                self._ploc(tok.value_loc),
                            )
                        )
                        return
                    concrete_id = self.gs.advance(fld)
                    if concrete_id is not False:
                        self.result[concrete_id] = False
                    return
            msg = self.formatter.explain_unknown_named(opt)
            self.errors.append((msg, self._ploc(tok.name_loc)))
            # Speculatively skip the next Value — likely this option's argument.
            if tok.value is None and queue and isinstance(queue[0], Value):
                queue.popleft()
            return

        # All bool flags?
        if all(not o.needs_value() for o in candidates):
            if tok.value is not None:
                self.errors.append(
                    (f"{opt} is a flag and does not take a value", self._ploc(tok.value_loc))
                )
                return
            best = _pick(candidates)
            concrete_id = self.gs.advance(best.field)
            if concrete_id is not False:
                self.result[concrete_id] = True
            return

        # Needs a value
        if tok.value is not None:
            value, value_loc = tok.value, self._ploc(tok.value_loc)
        else:
            res = self._consume_value(self._ploc(tok.name_loc), queue, name=opt)
            if res is None:
                return
            value, value_loc = res

        best = _pick(candidates, value)
        if best is None:
            self.errors.append((f"No matching option for {opt}={value!r}", value_loc))
            return
        self._advance(best, value, value_loc)

    @ovld
    def _handle(self, tok: ShortOpt, queue: deque) -> None:
        chars = tok.chars[1:]
        argv = tok.chars_loc.argv
        idx = tok.chars_loc.arg_index
        base = tok.chars_loc.start

        i = 0
        while i < len(chars):
            ch = chars[i]
            opt = f"-{ch}"
            char_loc = self._ploc(Loc(argv, idx, base + i, base + i + 1))
            candidates = self.candidates(opt)

            if not candidates:
                full_loc = self._ploc(Loc(argv, idx, 0 if i == 0 else base + i, base + i + 1))
                msg = self.formatter.explain_unknown_named(opt)
                self.errors.append((msg, full_loc))
                i += 1
                continue

            if all(not o.needs_value() for o in candidates):
                best = _pick(candidates)
                concrete_id = self.gs.advance(best.field)
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

            best = _pick(candidates, value)
            if best is None:
                self.errors.append((f"Unknown option: -{ch}", char_loc))
                break
            self._advance(best, value, value_loc)
            break  # value consumed — remaining chars were the value

    @ovld
    def _handle(self, tok: Value, queue: deque) -> None:
        candidates = self.candidates("*")
        best = _pick(candidates, tok.text)
        if best is None:
            self.errors.append(
                (f"Unexpected positional argument: {tok.text!r}", self._ploc(tok.loc))
            )
            return
        self._advance(best, tok.text, self._ploc(tok.loc))

    @ovld
    def _handle(self, tok: Separator, queue: deque) -> None:
        pass

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self, tokens: list) -> dict[str, Any]:
        queue: deque = deque(tokens)
        while queue:
            self._handle(queue.popleft(), queue)
        return self.result
