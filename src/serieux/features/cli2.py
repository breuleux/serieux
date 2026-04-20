"""
Command-line argument parser built on linearize (second attempt).
"""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from typing import Any

from ovld import Medley, ovld, recurse

from .dotted import unflatten
from .linearize import LinearField, LinearGroup, LinearUnlock, linearize
from .tagset import tag_field
from ..ctx import Context
from ..model import ListModelizable


# ═══════════════════════════════════════════════════════════════════════════════
# Source location
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Loc:
    """Character-level source location within an argv list."""

    argv: list[str]
    arg_index: int  # 0-based index into argv
    start: int      # inclusive char offset within argv[arg_index]
    end: int        # exclusive char offset within argv[arg_index]

    def render(self, message: str, color: bool = None) -> str:
        if color is None:
            color = sys.stderr.isatty()
        offsets = []
        pos = 0
        for arg in self.argv:
            offsets.append(pos)
            pos += len(arg) + 1
        abs_start = offsets[self.arg_index] + self.start
        abs_end = offsets[self.arg_index] + self.end
        width = max(1, abs_end - abs_start)
        arg_line = " ".join(self.argv)
        err_col = "\033[1;31m" if color else ""
        reset = "\033[0m" if color else ""
        underline = " " * abs_start + err_col + "^" * width + reset
        return f"{message}\n\n  {arg_line}\n  {underline}"

    def __add__(self, other: "Loc") -> "Loc":
        """Merge two locations within the same argv element."""
        assert self.argv is other.argv and self.arg_index == other.arg_index
        return Loc(self.argv, self.arg_index, min(self.start, other.start), max(self.end, other.end))


# ═══════════════════════════════════════════════════════════════════════════════
# Tokens
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class LongOpt:
    """A --name or --name=value token.

    ``name_loc`` covers ``--name``.
    ``value`` / ``value_loc`` are set only when ``=`` is present.
    """

    name: str
    name_loc: Loc
    value: str | None = None
    value_loc: Loc | None = None


@dataclass
class ShortOpt:
    """A short-option cluster like ``-xyz`` or ``-x=val``.

    ``chars`` is the run of flag characters (e.g. ``'xyz'``).
    ``chars_loc`` covers just those characters (after the leading ``-``).
    ``value`` / ``value_loc`` are set only when ``=`` is present.
    """

    chars: str
    chars_loc: Loc
    value: str | None = None
    value_loc: Loc | None = None


@dataclass
class Value:
    """A bare positional value."""

    text: str
    loc: Loc


@dataclass
class Separator:
    """The ``--`` end-of-options sentinel."""

    loc: Loc


Token = LongOpt | ShortOpt | Value | Separator


def tokenize(argv: list[str]) -> list[Token]:
    """Convert an argv list into a sequence of typed tokens with source locations.

    * ``--``        → :class:`Separator`; all following args become :class:`Value`.
    * ``--name``    → :class:`LongOpt` (``value=None``).
    * ``--name=v``  → :class:`LongOpt` (``value='v'``).
    * ``-x``        → :class:`ShortOpt` (``chars='x'``).
    * ``-xyz``      → :class:`ShortOpt` (``chars='xyz'``).
    * ``-x=v``      → :class:`ShortOpt` (``chars='x'``, ``value='v'``).
    * anything else → :class:`Value` (including bare ``-``).
    """
    tokens: list[Token] = []
    past_separator = False

    for idx, arg in enumerate(argv):
        def _loc(start: int, end: int, _i: int = idx) -> Loc:
            return Loc(argv, _i, start, end)

        if past_separator:
            tokens.append(Value(text=arg, loc=_loc(0, len(arg))))
            continue

        if arg == "--":
            tokens.append(Separator(loc=_loc(0, 2)))
            past_separator = True
            continue

        if arg.startswith("--"):
            body = arg[2:]
            if "=" in body:
                eq = body.index("=")
                name, val = body[:eq], body[eq + 1:]
                tokens.append(LongOpt(
                    name=name,
                    name_loc=_loc(0, 2 + eq),
                    value=val,
                    value_loc=_loc(2 + eq + 1, len(arg)),
                ))
            else:
                tokens.append(LongOpt(name=body, name_loc=_loc(0, len(arg))))
            continue

        if arg.startswith("-") and len(arg) >= 2 and arg[1] != "-":
            chars_raw = arg[1:]
            if "=" in chars_raw:
                eq = chars_raw.index("=")
                chars, val = chars_raw[:eq], chars_raw[eq + 1:]
                tokens.append(ShortOpt(
                    chars=chars,
                    chars_loc=_loc(1, 1 + eq),
                    value=val,
                    value_loc=_loc(1 + eq + 1, len(arg)),
                ))
            else:
                tokens.append(ShortOpt(chars=chars_raw, chars_loc=_loc(1, len(arg))))
            continue

        tokens.append(Value(text=arg, loc=_loc(0, len(arg))))

    return tokens


# ═══════════════════════════════════════════════════════════════════════════════
# Errors
# ═══════════════════════════════════════════════════════════════════════════════


class ParseError(Exception):
    def __init__(self, message: str, loc: Loc = None):
        super().__init__(message)
        self.loc = loc

    def __str__(self) -> str:
        msg = self.args[0]
        return self.loc.render(msg) if self.loc is not None else msg


# ═══════════════════════════════════════════════════════════════════════════════
# Option naming
# ═══════════════════════════════════════════════════════════════════════════════


_TAG_SUFFIX = f".{tag_field}"


def _strip_tag_suffix(path: str) -> str:
    return path[: -len(_TAG_SUFFIX)] if path.endswith(_TAG_SUFFIX) else path


def _cli_name(s: str) -> str:
    return s.replace("_", "-")


def _option_strings(lfield: LinearField) -> tuple[list[str], list[str]]:
    """Return ``(primary_names, alias_names)`` without leading ``--``.

    Primary names are ``[long, short]`` (e.g. ``['abc.def', 'def']``) or just
    ``[long]`` when both are identical.  Aliases come from field metadata.
    """
    f = lfield.field
    eff = _strip_tag_suffix(lfield.path)

    if f is not None and (opt := f.metadata.get("option")):
        primary = [opt.lstrip("-")]
    else:
        long = _cli_name(eff)
        short = _cli_name(eff.split(".")[-1])
        primary = [long] if long == short else [long, short]

    if f is not None:
        aliases = f.metadata.get("alias", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        aliases = [a.lstrip("-") for a in aliases]
    else:
        aliases = []

    return primary, aliases


# ═══════════════════════════════════════════════════════════════════════════════
# Handlers
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ChoiceSet:
    """Multiple ``LinearUnlock``s for the same path/group, disambiguated by value.

    Sorted so entries with a concrete ``expected_value`` come before ``None``.
    """

    unlocks: list[LinearUnlock]


@dataclass
class Ambiguous:
    """A short-name collision — user must use a long-form alternative."""

    alternatives: list[str]  # e.g. ["--abc.def", "--xyz.def"]


Handler = LinearField | ChoiceSet | Ambiguous


def _group_handlers(fields: list[LinearField]) -> list[LinearField | ChoiceSet]:
    """Group ``LinearUnlock``s sharing the same ``(path, group_id)`` into a
    :class:`ChoiceSet`; leave all other fields separate.
    """
    unlock_map: dict[tuple[str, str], list[LinearUnlock]] = {}
    unlock_order: list[tuple[str, str]] = []
    result: list = []

    for f in fields:
        if isinstance(f, LinearUnlock):
            key = (f.path, f.group_id)
            if key not in unlock_map:
                unlock_map[key] = []
                unlock_order.append(key)
            unlock_map[key].append(f)
        else:
            result.append(f)

    for key in unlock_order:
        unlocks = unlock_map[key]
        # Most specific (expected_value set) before generic (None)
        unlocks.sort(key=lambda u: u.expected_value is None)
        result.append(ChoiceSet(unlocks=unlocks) if len(unlocks) > 1 else unlocks[0])

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Result
# ═══════════════════════════════════════════════════════════════════════════════


class ParsedArgs(dict):
    """Nested dict result with per-path source locations."""

    def __init__(self, data: dict, spans: dict[str, Loc]) -> None:
        super().__init__(data)
        self.spans = spans


# ═══════════════════════════════════════════════════════════════════════════════
# Parser
# ═══════════════════════════════════════════════════════════════════════════════


class ParserState:
    def __init__(self, root_group: LinearGroup) -> None:
        self.option_map: dict[str, Handler] = {}
        self.pos_queue: list[LinearField | ChoiceSet] = []
        self.latent: dict[str, list[LinearGroup]] = {}   # group_id → branches
        self.activated: dict[str, int] = {}              # group_id → choice_id
        self.result: dict[str, Any] = {}
        self.spans: dict[str, Loc] = {}
        self._add_group(root_group)

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _add_group(self, group: LinearGroup) -> None:
        """Register a group's latent branches then activate its fields as a batch."""
        for gid, branches in group.option_groups.items():
            self.latent[gid] = branches
        self._add_batch(group.fields)

    def _add_batch(self, fields: list[LinearField]) -> None:
        """Add a list of fields with intra-batch collision detection.

        Within this batch, if two non-compatible handlers map to the same option
        string, that string is replaced with an :class:`Ambiguous` entry.
        Handlers from previous batches are overwritten by the new batch's entry
        for the same key (no cross-batch collision check).
        """
        positionals_raw: list[LinearField] = []
        options: list[LinearField] = []
        for f in fields:
            meta = f.field.metadata if f.field is not None else {}
            if meta.get("positional", False):
                positionals_raw.append(f)
            else:
                options.append(f)

        # Collect all LinearFields per option string within this batch
        str_to_fields: dict[str, list[LinearField]] = {}
        for f in options:
            primary, aliases = _option_strings(f)
            for name in primary + aliases:
                str_to_fields.setdefault(name, []).append(f)

        # Build a handler for each option string
        batch_handlers: dict[str, Handler] = {}
        for opt_str, fs in str_to_fields.items():
            groups = _group_handlers(fs)
            if len(groups) == 1:
                batch_handlers[opt_str] = groups[0]
            else:
                # Collision: mark short name as ambiguous; long names are unique
                alts: list[str] = []
                for g in groups:
                    src = g.unlocks[0] if isinstance(g, ChoiceSet) else g
                    prim, _ = _option_strings(src)
                    alts.append(f"--{prim[0]}")
                batch_handlers[opt_str] = Ambiguous(alternatives=alts)

        # New batch overwrites whatever was previously registered for these keys
        self.option_map.update(batch_handlers)

        # Group positional unlocks with the same (path, group_id) into ChoiceSets,
        # preserving order of first appearance.
        unlock_groups: dict[tuple[str, str], list[LinearUnlock]] = {}
        unlock_order: list[tuple[str, str]] = []
        pos_handlers: list[LinearField | ChoiceSet] = []
        for f in positionals_raw:
            if isinstance(f, LinearUnlock):
                key = (f.path, f.group_id)
                if key not in unlock_groups:
                    unlock_groups[key] = []
                    unlock_order.append(key)
                unlock_groups[key].append(f)
            else:
                pos_handlers.append(f)
        for key in unlock_order:
            unlocks = unlock_groups[key]
            unlocks.sort(key=lambda u: u.expected_value is None)
            pos_handlers.append(ChoiceSet(unlocks=unlocks) if len(unlocks) > 1 else unlocks[0])
        self.pos_queue.extend(pos_handlers)

    # ── Unlock ─────────────────────────────────────────────────────────────────

    def _resolve_unlock(
        self,
        unlocks: list[LinearUnlock],
        value: Any,
        value_loc: Loc,
        key_loc: Loc,
    ) -> LinearUnlock:
        """Find the first unlock whose ``expected_value`` matches *value*."""
        for u in unlocks:  # already sorted: specific first, None last
            if u.expected_value is None or u.expected_value == value:
                return u
        candidates = [u.expected_value for u in unlocks if u.expected_value is not None]
        # All specific → tagged union; give a more targeted error
        if all(u.expected_value is not None for u in unlocks):
            raise ParseError(f"Unknown tag {value!r}. Valid tags: {candidates}", value_loc)
        raise ParseError(f"Unexpected value {value!r}; expected one of {candidates}", value_loc)

    def _fire_unlock(
        self,
        unlock: LinearUnlock,
        value: Any,
        value_loc: Loc,
        key_loc: Loc,
    ) -> None:
        gid = unlock.group_id
        if gid in self.activated:
            if self.activated[gid] != unlock.choice_id:
                raise ParseError(
                    "Conflicting choices: a different branch was already selected",
                    key_loc,
                )
            # Same branch already active — just update the stored value
        else:
            self.activated[gid] = unlock.choice_id
            self._add_group(self.latent[gid][unlock.choice_id])
        self.result[unlock.path] = value
        self.spans[unlock.path] = value_loc

    # ── Field assignment ───────────────────────────────────────────────────────

    @staticmethod
    def _coerce(tp: type, value: str) -> Any:
        """Convert a CLI string to a primitive Python type when possible."""
        if not isinstance(value, str):
            return value  # already coerced (e.g. True from a bool flag)
        try:
            if tp is int:
                return int(value)
            if tp is float:
                return float(value)
        except (ValueError, TypeError):
            pass
        return value

    def _set_field(self, lfield: LinearField, value: Any, loc: Loc) -> None:
        path = lfield.path
        try:
            is_list = issubclass(lfield.type, ListModelizable)
        except TypeError:
            is_list = False
        if is_list:
            from ..model import model as _model
            m = _model(lfield.type)
            elem_tp = m.element_field.type if (m and m.element_field) else str
            coerced = self._coerce(elem_tp, value)
            existing = self.result.get(path, [])
            self.result[path] = (existing if isinstance(existing, list) else [existing]) + [coerced]
        else:
            self.result[path] = self._coerce(lfield.type, value)
        self.spans[path] = loc

    # ── Dispatch ───────────────────────────────────────────────────────────────

    def _needs_value(self, handler: Handler) -> bool:
        """Return True if this handler must consume a value token from the stream."""
        if isinstance(handler, Ambiguous):
            return True
        if isinstance(handler, ChoiceSet):
            # A ChoiceSet of bool unlocks fires as a flag (no value token consumed)
            return handler.unlocks[0].type is not bool
        if isinstance(handler, LinearUnlock):
            return handler.type is not bool
        return handler.type is not bool

    def _apply_handler(
        self,
        handler: Handler,
        value: Any,
        value_loc: Loc,
        key_loc: Loc,
    ) -> None:
        """Apply *handler* with a value already consumed from the token stream."""
        if isinstance(handler, Ambiguous):
            raise ParseError(
                f"Ambiguous option; use one of: {', '.join(handler.alternatives)}",
                key_loc,
            )
        elif isinstance(handler, ChoiceSet):
            unlock = self._resolve_unlock(handler.unlocks, value, value_loc, key_loc)
            self._fire_unlock(unlock, value, value_loc, key_loc)
        elif isinstance(handler, LinearUnlock):
            self._fire_unlock(handler, value, value_loc, key_loc)
        else:
            self._set_field(handler, value, value_loc)

    def _apply_bool_handler(self, handler: Handler, loc: Loc) -> None:
        """Apply a flag-style (no-value) handler, setting True / firing bool unlocks."""
        if isinstance(handler, ChoiceSet):
            unlock = self._resolve_unlock(handler.unlocks, True, loc, loc)
            self._fire_unlock(unlock, True, loc, loc)
        elif isinstance(handler, LinearUnlock):
            self._fire_unlock(handler, True, loc, loc)
        else:
            assert isinstance(handler, LinearField)
            self.result[handler.path] = True
            self.spans[handler.path] = loc

    # ── Token handlers ─────────────────────────────────────────────────────────

    def _consume_value(self, key_loc: Loc, queue: deque[Token]) -> tuple[str, Loc]:
        """Pop the next :class:`Value` token or raise :class:`ParseError`."""
        if not queue or not isinstance(queue[0], Value):
            raise ParseError("Expected a value", key_loc)
        tok = queue.popleft()
        return tok.text, tok.loc

    def _handle_long(self, tok: LongOpt, queue: deque[Token]) -> None:
        opt = tok.name
        if opt not in self.option_map:
            # Support --no-X negation for regular bool fields only (not unlocks)
            if opt.startswith("no-"):
                base = opt[3:]
                h = self.option_map.get(base)
                if isinstance(h, LinearField) and not isinstance(h, LinearUnlock) and h.type is bool:
                    if tok.value is not None:
                        raise ParseError(
                            f"--{opt} is a flag and does not take a value", tok.value_loc
                        )
                    self.result[h.path] = False
                    self.spans[h.path] = tok.name_loc
                    return
            raise ParseError(f"Unknown option: --{opt}", tok.name_loc)

        handler = self.option_map[opt]

        if not self._needs_value(handler):
            if tok.value is not None:
                raise ParseError(f"--{opt} is a flag and does not take a value", tok.value_loc)
            self._apply_bool_handler(handler, tok.name_loc)
            return

        value, value_loc = (
            (tok.value, tok.value_loc)
            if tok.value is not None
            else self._consume_value(tok.name_loc, queue)
        )
        self._apply_handler(handler, value, value_loc, tok.name_loc)

    def _handle_short(self, tok: ShortOpt, queue: deque[Token]) -> None:
        chars = tok.chars
        argv = tok.chars_loc.argv
        idx = tok.chars_loc.arg_index
        base = tok.chars_loc.start  # offset of chars[0] within argv[idx]

        i = 0
        while i < len(chars):
            ch = chars[i]
            char_loc = Loc(argv, idx, base + i, base + i + 1)

            if ch not in self.option_map:
                raise ParseError(f"Unknown option: -{ch}", char_loc)

            handler = self.option_map[ch]

            if not self._needs_value(handler):
                # Bool flag: fire and continue walking the cluster
                self._apply_bool_handler(handler, char_loc)
                i += 1
                continue

            # Needs a value: rest of chars cluster, then inline =val, then next token
            rest = chars[i + 1:]
            if rest:
                rest_loc = Loc(argv, idx, base + i + 1, tok.chars_loc.end)
                value, value_loc = rest, rest_loc
            elif tok.value is not None:
                value, value_loc = tok.value, tok.value_loc
            else:
                value, value_loc = self._consume_value(char_loc, queue)

            self._apply_handler(handler, value, value_loc, char_loc)
            break  # value consumed — remaining chars were the value

    def _handle_positional(self, tok: Value) -> None:
        if not self.pos_queue:
            raise ParseError(f"Unexpected positional argument: {tok.text!r}", tok.loc)
        handler = self.pos_queue[0]
        # Retrieve positional metadata from the underlying field
        if isinstance(handler, ChoiceSet):
            src_field = handler.unlocks[0].field
        else:
            src_field = handler.field
        pos_meta = src_field.metadata.get("positional", False) if src_field else True
        remainder = pos_meta not in (False, True)
        self._apply_handler(handler, tok.text, tok.loc, tok.loc)
        if not remainder:
            self.pos_queue.pop(0)

    # ── Validation ─────────────────────────────────────────────────────────────

    def _check_required(self) -> None:
        missing: list[str] = []
        seen_paths: set[str] = set()

        for handler in self.option_map.values():
            if isinstance(handler, Ambiguous):
                continue
            src: LinearField = handler.unlocks[0] if isinstance(handler, ChoiceSet) else handler
            if src.path in seen_paths:
                continue
            seen_paths.add(src.path)
            if src.field is not None and src.field.required and src.path not in self.result:
                prim, _ = _option_strings(src)
                missing.append(f"--{prim[0]}")

        for h in self.pos_queue:
            src = h.unlocks[0] if isinstance(h, ChoiceSet) else h
            pos_meta = src.field.metadata.get("positional", False) if src.field else True
            remainder = pos_meta not in (False, True)
            if not remainder and src.field is not None and src.field.required and src.path not in self.result:
                missing.append((src.field.name or src.path.split(".")[-1]).upper())

        if missing:
            noun = "arguments" if len(missing) > 1 else "argument"
            raise ParseError(f"Missing required {noun}: {', '.join(missing)}")

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self, tokens: list[Token]) -> ParsedArgs:
        queue: deque[Token] = deque(tokens)
        while queue:
            tok = queue.popleft()
            if isinstance(tok, Separator):
                continue  # tokenizer already converts post-separator args to Value
            elif isinstance(tok, LongOpt):
                self._handle_long(tok, queue)
            elif isinstance(tok, ShortOpt):
                self._handle_short(tok, queue)
            else:
                self._handle_positional(tok)
        self._check_required()
        return ParsedArgs(unflatten(self.result), self.spans)


# ═══════════════════════════════════════════════════════════════════════════════
# Public interface
# ═══════════════════════════════════════════════════════════════════════════════


def parse(root_type: type, argv: list[str] = None) -> ParsedArgs:
    """Parse *argv* (defaults to ``sys.argv[1:]``) against *root_type*'s schema."""
    if argv is None:
        argv = sys.argv[1:]
    tokens = tokenize(argv)
    group = linearize(root_type)
    state = ParserState(group)
    return state.run(tokens)


# Alias for compatibility
parse_cli = parse


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
