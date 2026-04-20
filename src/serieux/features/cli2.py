"""
Command-line argument parser built on linearize (second attempt).
"""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from typing import Any

from ovld import Medley, ovld, recurse

from ..ctx import Context
from ..model import ListModelizable
from .dotted import unflatten
from .linearize import LinearField, LinearGroup, LinearUnlock, linearize
from .tagset import tag_field

# ═══════════════════════════════════════════════════════════════════════════════
# Source location
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Loc:
    """Character-level source location within an argv list.

    When ``phantom=True`` the location does not point to real characters but
    to ``end`` imaginary characters inserted right *after* ``argv[arg_index]``
    in the rendered output, to indicate where something is *missing*.
    """

    argv: list[str]
    arg_index: int  # 0-based index into argv
    start: int  # char offset within argv[arg_index]  (0 if phantom)
    end: int  # exclusive end  (phantom width if phantom)
    prog: str | None = None  # program name shown dimmed before the arg line
    phantom: bool = False  # if True, insert phantom chars after argv[arg_index]
    phantom_char: str = " "  # character used for the phantom display area

    def render(self, message: str, color: bool = None) -> str:
        return _render_all_errors([(message, self)], color)

    def __add__(self, other: "Loc") -> "Loc":
        """Merge two locations within the same argv element."""
        assert self.argv is other.argv and self.arg_index == other.arg_index
        return Loc(
            self.argv,
            self.arg_index,
            min(self.start, other.start),
            max(self.end, other.end),
            self.prog,
        )


def _colorize_labeled(chars: list[str], err_col: str, reset: str) -> str:
    """Join underline chars, wrapping every non-space run in ANSI error color."""
    if not err_col:
        return "".join(chars)
    result: list[str] = []
    in_err = False
    for ch in chars:
        if ch != " " and not in_err:
            result.append(err_col)
            in_err = True
        elif ch == " " and in_err:
            result.append(reset)
            in_err = False
        result.append(ch)
    if in_err:
        result.append(reset)
    return "".join(result)


def _render_all_errors(
    items: list[tuple[str, "Loc | None"]],
    color: bool = None,
) -> str:
    """Render a list of ``(message, loc)`` pairs.

    Each item is listed as ``a. message``, ``b. message``, … and its span in
    the arg line is underlined with ``^…^X`` where X is the assigned letter.
    Items without a loc still receive a letter in the listing but have no
    underline.  Phantom spans insert extra chars right after their token.
    """
    if color is None:
        color = sys.stderr.isatty()
    if not items:
        return ""

    # Assign a letter to each item (all items get a letter for consistency)
    letters = [chr(ord("a") + i) for i in range(len(items))]

    # Build message listing
    message_lines = [f"{letter}. {msg}" for letter, (msg, _) in zip(letters, items)]

    # Find the first item that has a loc (for argv / prog context)
    first_loc = next((loc for _, loc in items if loc is not None), None)
    if first_loc is None:
        return "\n".join(message_lines)

    argv = first_loc.argv
    prog = first_loc.prog

    # Lettered spans: only items that have a loc
    lettered: list[tuple[str, "Loc"]] = [
        (letter, loc) for letter, (_, loc) in zip(letters, items) if loc is not None
    ]

    err_col = "\033[1;31m" if color else ""
    dim = "\033[2m" if color else ""
    reset = "\033[0m" if color else ""

    # Determine phantom width, display char, and active ranges per arg index.
    # Active ranges are positions [start, end) within the phantom area that are
    # covered by a label; gaps between them become plain spaces in the display.
    phantom_width: dict[int, int] = {}
    phantom_char_for: dict[int, str] = {}
    phantom_active: dict[int, list[tuple[int, int]]] = {}
    for _, loc in lettered:
        if loc.phantom:
            phantom_width[loc.arg_index] = max(phantom_width.get(loc.arg_index, 0), loc.end)
            phantom_char_for[loc.arg_index] = loc.phantom_char
            phantom_active.setdefault(loc.arg_index, []).append((loc.start, loc.end))

    # Build plain display (for offset math) and colored display (for rendering).
    # Non-space phantom chars get an extra leading space and are rendered grey;
    # positions not covered by any active range become plain spaces.
    # phant_offsets is a dict so it can also hold "trailing" phantoms whose
    # arg_index >= len(argv) (e.g. when argv is empty).
    real_offsets: list[int] = []
    phant_offsets: dict[int, int | None] = {}
    plain_parts: list[str] = []
    color_parts: list[str] = []
    pos = 0
    for i, arg in enumerate(argv):
        real_offsets.append(pos)
        plain_parts.append(arg)
        color_parts.append(arg)
        pos += len(arg)
        pw = phantom_width.get(i, 0)
        pc = phantom_char_for.get(i, " ")
        if pw:
            if pc != " ":
                active = set()
                for s, e in phantom_active.get(i, []):
                    active.update(range(s, e))
                chars = "".join(pc if j in active else " " for j in range(pw))
                plain_parts.append(" " + chars)
                color_parts.append(" " + dim + chars + reset)
                phant_offsets[i] = pos + 1
                pos += 1 + pw
            else:
                plain_parts.append(" " * pw)
                color_parts.append(" " * pw)
                phant_offsets[i] = pos
                pos += pw
        else:
            phant_offsets[i] = None
        if i < len(argv) - 1:
            plain_parts.append(" ")
            color_parts.append(" ")
            pos += 1

    # Trailing phantoms: arg_index >= len(argv).  These are appended after all
    # real args (or are the entire display when argv is empty).
    for idx in sorted(
        {loc.arg_index for _, loc in lettered if loc.phantom and loc.arg_index >= len(argv)}
    ):
        pw = phantom_width.get(idx, 0)
        pc = phantom_char_for.get(idx, " ")
        if not pw:
            phant_offsets[idx] = None
            continue
        active = set()
        for s, e in phantom_active.get(idx, []):
            active.update(range(s, e))
        chars = "".join(pc if j in active else " " for j in range(pw))
        if pos > 0:  # separate from preceding real args
            plain_parts.append(" ")
            color_parts.append(" ")
            pos += 1
        if pc != " ":
            plain_parts.append(chars)
            color_parts.append(dim + chars + reset)
        else:
            plain_parts.append(chars)
            color_parts.append(chars)
        phant_offsets[idx] = pos
        pos += pw

    display = "".join(plain_parts)
    display_color = "".join(color_parts)
    uc = [" "] * len(display)

    for letter, loc in lettered:
        if loc.phantom:
            po = phant_offsets[loc.arg_index]
            if po is None:
                continue
            a, b = po + loc.start, po + loc.end
        else:
            a = real_offsets[loc.arg_index] + loc.start
            b = real_offsets[loc.arg_index] + loc.end
        a, b = max(0, a), min(b, len(uc))
        if b <= a:
            continue
        for j in range(a, b - 1):
            uc[j] = "^"
        uc[b - 1] = letter  # last char of span is the letter label

    underline = _colorize_labeled(uc, err_col, reset)

    if prog:
        prefix = len(prog) + 1
        line = f"{dim}{prog}{reset} {display_color}"
        under = " " * prefix + underline
    else:
        line = display_color
        under = underline

    header = "\n".join(message_lines)
    return f"{header}\n\n  {line}\n  {under}"


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


def _token_argv(tok: Token) -> list[str]:
    """Return the shared argv list carried by any token type."""
    if isinstance(tok, LongOpt):
        return tok.name_loc.argv
    if isinstance(tok, ShortOpt):
        return tok.chars_loc.argv
    return tok.loc.argv


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
                name, val = body[:eq], body[eq + 1 :]
                tokens.append(
                    LongOpt(
                        name=name,
                        name_loc=_loc(0, 2 + eq),
                        value=val,
                        value_loc=_loc(2 + eq + 1, len(arg)),
                    )
                )
            else:
                tokens.append(LongOpt(name=body, name_loc=_loc(0, len(arg))))
            continue

        if arg.startswith("-") and len(arg) >= 2 and arg[1] != "-":
            chars_raw = arg[1:]
            if "=" in chars_raw:
                eq = chars_raw.index("=")
                chars, val = chars_raw[:eq], chars_raw[eq + 1 :]
                tokens.append(
                    ShortOpt(
                        chars=chars,
                        chars_loc=_loc(1, 1 + eq),
                        value=val,
                        value_loc=_loc(1 + eq + 1, len(arg)),
                    )
                )
            else:
                tokens.append(ShortOpt(chars=chars_raw, chars_loc=_loc(1, len(arg))))
            continue

        tokens.append(Value(text=arg, loc=_loc(0, len(arg))))

    return tokens


# ═══════════════════════════════════════════════════════════════════════════════
# Errors
# ═══════════════════════════════════════════════════════════════════════════════


class ParseError(Exception):
    """Holds one or more located error messages, rendered together."""

    def __init__(self, message: str, loc: Loc = None):
        super().__init__(message)
        self.loc = loc
        self._items: list[tuple[str, Loc | None]] = [(message, loc)]

    @classmethod
    def _from_items(cls, items: list[tuple[str, Loc | None]]) -> "ParseError":
        obj = cls.__new__(cls)
        first_msg = items[0][0] if items else ""
        first_loc = items[0][1] if items else None
        Exception.__init__(obj, first_msg)
        obj.loc = first_loc
        obj._items = list(items)
        return obj

    def __str__(self) -> str:
        return _render_all_errors(self._items)


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
# Control structure
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(kw_only=True)
class Control:
    # [alias: -h]
    help: bool = False

    def build(self, flat, spans, parse_error):
        if parse_error is not None:
            raise parse_error
        return ParsedArgs(unflatten(flat), spans)


# Internal namespace used to segregate Control fields from root-type fields.
# Using a dotted prefix with a non-identifier first segment ensures it can
# never clash with user-defined field names (identifiers cannot start with a
# digit).  The leading digit also prevents _cli_name from producing a leading
# dash, while the fields still surface under their short names (e.g. ``help``)
# and any aliases (e.g. ``-h``).
_CTRL_NS = "0ctrl"


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
    def __init__(self, root_group: LinearGroup, prog: str | None = None) -> None:
        self.option_map: dict[str, Handler] = {}
        self.pos_queue: list[LinearField | ChoiceSet] = []
        self.latent: dict[str, list[LinearGroup]] = {}  # group_id → branches
        self.activated: dict[str, int] = {}  # group_id → choice_id
        self.result: dict[str, Any] = {}
        self.spans: dict[str, Loc] = {}
        self.prog: str | None = prog
        self._accumulated: list[tuple[str, Loc | None]] = []
        self._errored_paths: set[str] = set()
        self._argv: list[str] = []        # populated by run()
        self._current_arg_idx: int = -1   # updated as tokens are consumed
        self._field_added_at: dict[str, int] = {}  # path → arg_index when added
        self._add_group(root_group)

    def _ploc(self, loc: Loc) -> Loc:
        """Return *loc* with ``prog`` stamped on, for use in raised errors."""
        if self.prog is None or loc.prog == self.prog:
            return loc
        from dataclasses import replace

        return replace(loc, prog=self.prog)

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
        for f in fields:
            self._field_added_at.setdefault(f.path, self._current_arg_idx)
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
            self._current_arg_idx = value_loc.arg_index
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
            self.result[path] = (existing if isinstance(existing, list) else [existing]) + [
                coerced
            ]
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

    def _mark_handler_errored(self, handler: Handler) -> None:
        """Record the path of *handler* so _check_required won't double-report it."""
        if isinstance(handler, Ambiguous):
            return
        src = handler.unlocks[0] if isinstance(handler, ChoiceSet) else handler
        self._errored_paths.add(src.path)

    def _missing_loc(self, key_loc: Loc) -> Loc:
        """Return a phantom loc that shows grey dots right after the key option token."""
        return Loc(
            argv=key_loc.argv,
            arg_index=key_loc.arg_index,
            start=0,
            end=2,
            prog=key_loc.prog,
            phantom=True,
            phantom_char="·",
        )

    def _consume_value(self, key_loc: Loc, queue: deque[Token]) -> tuple[str, Loc]:
        """Pop the next :class:`Value` token or raise :class:`ParseError`."""
        if not queue or not isinstance(queue[0], Value):
            raise ParseError("Expected a value", self._missing_loc(key_loc))
        tok = queue.popleft()
        return tok.text, self._ploc(tok.loc)

    def _handle_long(self, tok: LongOpt, queue: deque[Token]) -> None:
        opt = tok.name
        if opt not in self.option_map:
            # Support --no-X negation for regular bool fields only (not unlocks)
            if opt.startswith("no-"):
                base = opt[3:]
                h = self.option_map.get(base)
                if (
                    isinstance(h, LinearField)
                    and not isinstance(h, LinearUnlock)
                    and h.type is bool
                ):
                    if tok.value is not None:
                        raise ParseError(
                            f"--{opt} is a flag and does not take a value",
                            self._ploc(tok.value_loc),
                        )
                    self.result[h.path] = False
                    self.spans[h.path] = tok.name_loc
                    return
            self._accumulated.append((f"Unknown option: --{opt}", self._ploc(tok.name_loc)))
            # Speculatively skip the next Value — likely this option's argument.
            if tok.value is None and queue and isinstance(queue[0], Value):
                queue.popleft()
            return

        handler = self.option_map[opt]

        if not self._needs_value(handler):
            if tok.value is not None:
                raise ParseError(
                    f"--{opt} is a flag and does not take a value",
                    self._ploc(tok.value_loc),
                )
            self._apply_bool_handler(handler, tok.name_loc)
            return

        if tok.value is not None:
            value, value_loc = tok.value, self._ploc(tok.value_loc)
        else:
            try:
                value, value_loc = self._consume_value(self._ploc(tok.name_loc), queue)
            except ParseError as e:
                self._accumulated.extend(e._items)
                self._mark_handler_errored(handler)
                return
        self._apply_handler(handler, value, value_loc, self._ploc(tok.name_loc))

    def _handle_short(self, tok: ShortOpt, queue: deque[Token]) -> None:
        chars = tok.chars
        argv = tok.chars_loc.argv
        idx = tok.chars_loc.arg_index
        base = tok.chars_loc.start  # offset of chars[0] within argv[idx]

        i = 0
        while i < len(chars):
            ch = chars[i]
            char_loc = self._ploc(Loc(argv, idx, base + i, base + i + 1))

            if ch not in self.option_map:
                # Extend loc to include the leading '-' for the first char
                full_loc = self._ploc(Loc(argv, idx, 0 if i == 0 else base + i, base + i + 1))
                self._accumulated.append((f"Unknown option: -{ch}", full_loc))
                i += 1
                continue

            handler = self.option_map[ch]

            if not self._needs_value(handler):
                # Bool flag: fire and continue walking the cluster
                self._apply_bool_handler(handler, char_loc)
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
                try:
                    value, value_loc = self._consume_value(char_loc, queue)
                except ParseError as e:
                    self._accumulated.extend(e._items)
                    self._mark_handler_errored(handler)
                    break
            self._apply_handler(handler, value, value_loc, char_loc)
            break  # value consumed — remaining chars were the value

    def _handle_positional(self, tok: Value) -> None:
        if not self.pos_queue:
            raise ParseError(f"Unexpected positional argument: {tok.text!r}", self._ploc(tok.loc))
        handler = self.pos_queue[0]
        # Retrieve positional metadata from the underlying field
        if isinstance(handler, ChoiceSet):
            src_field = handler.unlocks[0].field
        else:
            src_field = handler.field
        pos_meta = src_field.metadata.get("positional", False) if src_field else True
        remainder = pos_meta not in (False, True)
        try:
            self._apply_handler(handler, tok.text, self._ploc(tok.loc), self._ploc(tok.loc))
        except ParseError as e:
            self._accumulated.extend(e._items)
            self._mark_handler_errored(handler)
            if not remainder:
                self.pos_queue.pop(0)
            return
        if not remainder:
            self.pos_queue.pop(0)

    # ── Validation ─────────────────────────────────────────────────────────────

    def _check_required(self) -> None:
        # Collect (message, added_at) where added_at is the arg_index when the
        # field became available (-1 = initial, falls back to end of argv).
        missing: list[tuple[str, int]] = []
        seen_paths: set[str] = set()

        for handler in self.option_map.values():
            if isinstance(handler, Ambiguous):
                continue
            src: LinearField = handler.unlocks[0] if isinstance(handler, ChoiceSet) else handler
            if src.path in seen_paths:
                continue
            seen_paths.add(src.path)
            if (
                src.field is not None
                and src.field.required
                and src.path not in self.result
                and src.path not in self._errored_paths
            ):
                prim, _ = _option_strings(src)
                missing.append((f"Missing required option: --{prim[0]}",
                                 self._field_added_at.get(src.path, -1)))

        for h in self.pos_queue:
            src = h.unlocks[0] if isinstance(h, ChoiceSet) else h
            pos_meta = src.field.metadata.get("positional", False) if src.field else True
            remainder = pos_meta not in (False, True)
            if (
                not remainder
                and src.field is not None
                and src.field.required
                and src.path not in self.result
                and src.path not in self._errored_paths
            ):
                name = (src.field.name or src.path.split(".")[-1]).upper()
                missing.append((f"Missing required argument: {name}",
                                 self._field_added_at.get(src.path, -1)))

        if not missing:
            return

        argv = self._argv
        last_idx = len(argv) - 1 if argv else 0  # trailing phantom index for empty argv

        # Group messages by the arg_index where the phantom should appear.
        # -1 (initial fields) falls back to last_idx.
        from collections import defaultdict
        groups: dict[int, list[str]] = defaultdict(list)
        for msg, added_at in missing:
            groups[added_at if added_at >= 0 else last_idx].append(msg)

        # For each group, stagger phantoms (2 dots + 1 space gap) starting after
        # any phantom already placed at that arg_index.
        for arg_idx, msgs in sorted(groups.items()):
            existing_end = max(
                (loc.end for _, loc in self._accumulated
                 if loc is not None and loc.phantom and loc.arg_index == arg_idx),
                default=0,
            )
            base = existing_end + 1 if existing_end else 0
            for i, msg in enumerate(msgs):
                start = base + 3 * i
                self._accumulated.append((msg, Loc(
                    argv=argv, arg_index=arg_idx,
                    start=start, end=start + 2,
                    prog=self.prog, phantom=True, phantom_char="·",
                )))

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self, tokens: list[Token]) -> ParsedArgs:
        self._argv = _token_argv(tokens[0]) if tokens else []
        queue: deque[Token] = deque(tokens)
        while queue:
            tok = queue.popleft()
            try:
                if isinstance(tok, Separator):
                    continue  # tokenizer already converts post-separator args to Value
                elif isinstance(tok, LongOpt):
                    self._handle_long(tok, queue)
                elif isinstance(tok, ShortOpt):
                    self._handle_short(tok, queue)
                else:
                    self._handle_positional(tok)
            except ParseError as e:
                self._accumulated.extend(e._items)
        self._check_required()
        if self._accumulated:
            raise ParseError._from_items(self._accumulated)
        return ParsedArgs(unflatten(self.result), self.spans)


# ═══════════════════════════════════════════════════════════════════════════════
# Public interface
# ═══════════════════════════════════════════════════════════════════════════════


def parse(
    root_type: type,
    argv: list[str] = None,
    prog: str | None = None,
) -> ParsedArgs:
    """Parse *argv* (defaults to ``sys.argv[1:]``) against *root_type*'s schema.

    *prog* is the program name shown in error messages; defaults to ``sys.argv[0]``.

    :class:`Control` flags (e.g. ``-h`` / ``--help``) are injected into the
    parser via an internal namespace so they coexist with *root_type*'s own
    fields without any path collision.  After parsing, :meth:`Control.build`
    is called; it may intercept the result (e.g. print help and exit) or
    return ``None`` to continue with normal deserialization.
    """
    if argv is None:
        argv = sys.argv[1:]
    if prog is None:
        prog = sys.argv[0]
    tokens = tokenize(argv)

    # Merge root-type fields with Control fields (in a private namespace).
    root_group = linearize(root_type)
    ctrl_group = linearize(Control, _CTRL_NS)
    merged_group = root_group | ctrl_group

    state = ParserState(merged_group, prog=prog)

    parse_error: ParseError | None = None
    try:
        result = state.run(tokens)
        flat = state.result
        spans = result.spans
    except ParseError as e:
        parse_error = e
        flat = state.result
        spans = state.spans

    # Extract Control values from the internal namespace and build the instance.
    ctrl_prefix = _CTRL_NS + "."
    ctrl_flat = {k[len(ctrl_prefix):]: v for k, v in flat.items() if k.startswith(ctrl_prefix)}
    control = Control(**ctrl_flat)

    # Strip Control fields from the result.
    clean_flat = {k: v for k, v in flat.items() if not k.startswith(ctrl_prefix)}
    clean_spans = {k: v for k, v in spans.items() if not k.startswith(ctrl_prefix)}

    return control.build(clean_flat, clean_spans, parse_error)


def parse_cli(root_type: type, argv: list[str] = None, prog: str | None = None) -> ParsedArgs:
    return parse(root_type, argv, prog)


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
