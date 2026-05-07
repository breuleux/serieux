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
from typing import Any, Iterable

from ovld import ovld

from ...features.tagset import tag_field
from ...linearize import GroupState, LinearField, flatten_group
from .errors import ParseError
from .tokenize import Loc, LongOpt, Separator, ShortOpt, ShortOptValue, Value

########
# Misc #
########


class Word:
    def __init__(self, word: str):
        self.value = word


@dataclass(kw_only=True)
class Control:
    """Global options"""

    # [alias: -h]
    # [no-no]
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

    def specificity(self, value) -> int:
        if self.field is not None and self.field.expected_value and value is not None:
            return 2 if value == self.field.expected_value else 0
        else:
            return 1

    @property
    def unlock(self):
        return self.field.unlock

    def advance(self, gs):
        return gs.advance(self.field)

    def consume(self, parser, key_loc, inline_value, queue):
        if inline_value is not None:
            return [inline_value.text], [inline_value.loc]
        vtok = parser._consume_value(key_loc, queue, self.key)
        if vtok is None:
            return [], []
        return [vtok.text], [vtok.loc]

    def act(self, parser, key, value=None):
        value = parser.deserialize(self.field.type, Word(value))
        parser.result[key] = value


@dataclass
class BooleanOption(Option):
    value: bool

    def consume(self, parser, key_loc, inline_value, queue):
        # Only honour explicit =val; ignore cluster-tail ShortOptValue
        if isinstance(inline_value, Value):
            return [inline_value.text], [inline_value.loc]
        return [], []

    def act(self, parser, key, value=None):
        if value is None:
            parser.result[key] = self.value
        elif value.lower() in ("0", "false", "no"):
            parser.result[key] = not self.value
        elif value.lower() in ("1", "true", "yes"):
            parser.result[key] = self.value
        else:
            raise ValueError(f"Invalid flag value for {self.key}: {value!r}")


@dataclass
class CountOption(Option):
    def advance(self, gs):
        return gs.concrete_id(self.field)

    def consume(self, parser, key_loc, inline_value, queue):
        return [], []

    def act(self, parser, key, value=None):
        parser.result[key] = parser.result.get(key, 0) + 1


@dataclass
class NargsOption(Option):
    nargs: int | str  # int N or '*'

    def consume(self, parser, key_loc, inline_value, queue):
        values, locs = [], []
        if inline_value is not None:
            values.append(inline_value.text)
            locs.append(inline_value.loc)
        if self.nargs == "*":
            while queue and isinstance(queue[0], Value):
                vtok = queue.popleft()
                values.append(vtok.text)
                locs.append(vtok.loc)
        else:
            for _ in range(self.nargs - len(values)):
                vtok = parser._consume_value(key_loc, queue, self.key)
                if vtok is None:
                    break
                values.append(vtok.text)
                locs.append(vtok.loc)
        return values, locs


@dataclass
class AmbiguousOption(Option):
    alternatives: list[str]
    original_options: list[Option]

    def consume(self, parser, key_loc, inline_value, queue):
        return self.original_options[0].consume(parser, key_loc, inline_value, queue)

    def act(self, parser, key, value=None):
        alts = " or ".join(self.alternatives)
        raise ValueError(f"{self.key} is ambiguous. Use {alts} instead.")


@ovld
def generate_options(t: type[bool], names: list[str], fld: LinearField):
    def noify(x):
        return f"--no-{x.lstrip('-')}"

    yield from [BooleanOption(name, fld, True) for name in names]
    if not fld.metadata.get("no-no", False):
        yield from [BooleanOption(noify(name), fld, False) for name in names]


@ovld
def generate_options(t: Any, names: list[str], fld: LinearField):
    if fld.metadata.get("count"):
        yield from [CountOption(name, fld) for name in names]
    elif (nargs := fld.metadata.get("nargs")) is not None:
        n = "*" if nargs == "*" else int(nargs)
        yield from [NargsOption(name, fld, n) for name in names]
    else:
        yield from [Option(name, fld) for name in names]


def _options(fld: LinearField) -> Iterable[str]:
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
    yield from generate_options(fld.field.type, names, fld)


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

    def _advance(self, opt: Option, values: list, locs: list, key_loc: Loc) -> None:
        fld = opt.field
        if fld is None:
            value = values[0] if values else None
            loc = locs[0] if locs else key_loc
            try:
                opt.act(self, None, value)
            except Exception as exc:
                self.error(str(exc), loc)
            return

        if fld.sequence and len(values) > 1:
            for v, l in zip(values, locs):
                concrete_id = opt.advance(self.gs)
                if concrete_id is False:
                    self.error(f"Cannot assign field {fld.identifier!r}", l)
                    return
                try:
                    opt.act(self, concrete_id, v)
                except Exception as exc:
                    self.error(str(exc), l)
            return

        concrete_id = opt.advance(self.gs)
        if concrete_id is False:
            self.error(f"Cannot assign field {fld.identifier!r}", key_loc)
            return
        value = " ".join(values) if values else None
        loc = locs[0] if locs else key_loc
        try:
            opt.act(self, concrete_id, value)
        except Exception as exc:
            self.error(str(exc), loc)

    def _consume_value(
        self, key_loc: Loc, queue: deque, name: str | None = None
    ) -> tuple[str, Loc] | None:
        if not queue or not isinstance(queue[0], Value):
            msg = f"Missing value for argument '{name}'" if name else "Expected a value"
            self.error(msg, key_loc)
            return None
        return queue.popleft()

    @cached_property
    def formatter(self):
        from .fmt import ArgparseFormatter

        return ArgparseFormatter(self)

    def error(self, message, loc):
        self.errors.append((message, loc))

    # ── Options names ─────────────────────────────────────────────────────────-

    def populate_options(self):
        group_key_opts: dict[tuple, list[Option]] = defaultdict(list)

        for group, fld, _ in flatten_group(self.gs.initial):
            if fld.positional:
                self.option_map["*"].append(Option("*", fld))
            else:
                for opt in _options(fld):
                    ulid = tuple((id(u.group), u.choice_id) for u in fld.unlock)
                    group_key_opts[(id(group), ulid, opt.key)].append(opt)

        for (_, _, key), opts in group_key_opts.items():
            if len(opts) > 1:
                alternatives = [next(iter(_options(o.field))).key for o in opts]
                self.option_map[key].append(
                    AmbiguousOption(
                        key=key,
                        field=None,
                        alternatives=alternatives,
                        original_options=opts,
                    )
                )
            else:
                for opt in opts:
                    self.option_map[key].append(opt)

    @cache
    def option_strings(self, fld: LinearField):
        return [opt.key for opt in _options(fld)]

    def candidates(self, key: str) -> list[LinearField]:
        """All eligible fields, key being an option or '*' if positional.

        Returned in state-dict order; the rightmost eligible match is last.
        """
        return [
            opt for opt in self.option_map[key] if opt.field is None or self.gs.eligible(opt.field)
        ]

    # ── Token handlers ─────────────────────────────────────────────────────────

    @ovld
    def _handle(self, tok: LongOpt, queue: deque) -> None:
        opt_name = tok.name
        candidates = self.candidates(opt_name)

        if not candidates:
            msg = self.formatter.explain_unknown_named(opt_name)
            self.error(msg, tok.name_loc)
            # Speculatively skip the next Value — likely this option's argument.
            if tok.value is None and queue and isinstance(queue[0], Value):
                queue.popleft()
            return

        inline = Value(tok.value, tok.value_loc) if tok.value is not None else None
        best = _pick(candidates, tok.value)
        values, locs = best.consume(self, tok.name_loc, inline, queue)

        # Recompute best using the first consumed value (matters for union discrimination)
        first_val = values[0] if values else None
        best = _pick(candidates, first_val)
        if best is None:
            loc = locs[0] if locs else tok.name_loc
            self.error(f"No matching option for {opt_name}={first_val!r}", loc)
            return

        self._advance(best, values, locs, tok.name_loc)

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
            char_loc = Loc(argv, idx, base + i, base + i + 1, prog=self.prog)
            candidates = self.candidates(opt)

            if not candidates:
                full_loc = Loc(argv, idx, 0 if i == 0 else base + i, base + i + 1, prog=self.prog)
                msg = self.formatter.explain_unknown_named(opt)
                self.error(msg, full_loc)
                i += 1
                continue

            rest = chars[i + 1:]
            if rest:
                rest_loc = Loc(argv, idx, base + i + 1, tok.chars_loc.end, prog=self.prog)
                inline = ShortOptValue(rest, rest_loc)
            elif tok.value is not None:
                inline = Value(tok.value, tok.value_loc)
            else:
                inline = None

            best = _pick(candidates, inline.text if inline else None)
            values, locs = best.consume(self, char_loc, inline, queue)

            first_val = values[0] if values else None
            best = _pick(candidates, first_val)
            if best is None:
                self.error(f"Unknown option: -{ch}", char_loc)
                break
            self._advance(best, values, locs, char_loc)
            if values:
                break  # value consumed — remaining chars were the value
            i += 1

    @ovld
    def _handle(self, tok: Value, queue: deque) -> None:
        candidates = self.candidates("*")
        best = _pick(candidates, tok.text)
        if best is None:
            self.error(f"Unexpected positional argument: {tok.text!r}", tok.loc)
            return
        self._advance(best, [tok.text], [tok.loc], tok.loc)

    @ovld
    def _handle(self, tok: Separator, queue: deque) -> None:
        pass

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self, tokens: list) -> dict[str, Any]:
        queue: deque = deque(tokens)
        while queue:
            self._handle(queue.popleft(), queue)
        return self.result
