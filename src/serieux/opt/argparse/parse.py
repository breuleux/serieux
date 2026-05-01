"""
Command-line argument parser built on GroupState (third attempt).

For each token we scan the current state to find eligible fields, picking the
rightmost one that matches. This lets sequences and union branches work naturally
as state evolves via GroupState.advance().
"""

from __future__ import annotations

import inspect
import sys
from collections import deque
from dataclasses import dataclass, field, make_dataclass
from typing import Any

from ovld import Medley, ovld, recurse
from ovld.utils import clsstring

from ...ctx import Context
from ...features.dotted import unflatten
from ...features.tagset import tag_field
from ...linearize import GroupState, LinearField, LinearState, linearize

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
# Option naming
# ═══════════════════════════════════════════════════════════════════════════════


def _cli_name(s: str) -> str:
    parts = [p for p in s.split(".") if not p.startswith("__")]
    return ".".join(parts).replace("_", "-")


def _option_strings(lfield: LinearField) -> tuple[list[str], list[str]]:
    """Return ``(primary_names, alias_names)`` without leading ``--``.

    Primary names are ``[long, short]`` (e.g. ``['abc.def', 'def']``) or just
    ``[long]`` when both are identical.  Aliases come from field metadata.

    For ``$class`` discriminator fields the parent field's identifier/name is
    used so the option appears as e.g. ``--animal`` rather than ``--animal.$class``.
    """
    f = lfield.field
    if f.serialized_name == tag_field and lfield.parent is not None:
        eff = lfield.parent.identifier
        short_sn = lfield.parent.field.serialized_name
    else:
        eff = lfield.identifier
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


# ═══════════════════════════════════════════════════════════════════════════════
# Tokenize
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
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _type_metavar(tp: type) -> str:
    """Short uppercase metavar for a type; empty string for bool flags."""
    if tp is bool:
        return ""
    if tp is str:
        return "TEXT"
    if tp is int:
        return "INT"
    if tp is float:
        return "FLOAT"
    return tp.__name__.upper()


def _class_doc(cls: type) -> str:
    """Class docstring, or '' for the auto-generated dataclass form."""
    doc = inspect.getdoc(cls) or ""
    # Python auto-generates "ClassName(field: type, ...)" for dataclasses.
    return "" if doc.startswith(cls.__name__ + "(") else doc


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


def _format_trigger(fld: LinearField) -> str:
    """Format a single trigger field as a human-readable prerequisite."""
    if fld.positional:
        if fld.expected_value is not None:
            return repr(fld.expected_value)
        return fld.field.serialized_name.upper() if fld.field.serialized_name else "ARG"
    primary, _ = _field_option_strings(fld)
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
            primary, aliases = _field_option_strings(fld)
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


# ═══════════════════════════════════════════════════════════════════════════════
# Parser
# ═══════════════════════════════════════════════════════════════════════════════


class Cli3Parser:
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


def _format_help(gs: GroupState, prog: str, root_type: type, color: bool = None) -> str:
    from dataclasses import MISSING

    if color is None:
        color = sys.stdout.isatty()

    bold = "\033[1m" if color else ""
    dim = "\033[2m" if color else ""
    green = "\033[32m" if color else ""
    yellow = "\033[33m" if color else ""
    reset = "\033[0m" if color else ""

    c_header = lambda s: f"{bold}{s}{reset}"
    c_opt = lambda s: f"{bold}{green}{s}{reset}"
    c_meta = lambda s: f"{yellow}{s}{reset}"
    c_dim = lambda s: f"{dim}{s}{reset}"
    c_prog = lambda s: f"{bold}{s}{reset}"

    def _is_control(fld: LinearField) -> bool:
        return any(isinstance(s, str) and s.startswith("__control") for s in fld.signature)

    # ── Build group_field_map: gid → union LinearField ─────────────────────────
    group_field_map: dict[str, LinearField] = {}
    for fld in gs.state:
        for ul in fld.unlock:
            if ul.group.identifier not in group_field_map:
                group_field_map[ul.group.identifier] = ul.group

    # ── Collect branch fields: gid → {cid → [LinearField]} ────────────────────
    latent_by_group: dict[str, dict[int, list[LinearField]]] = {}
    for gid, subgroups in gs._option_groups.items():
        for cid, subgroup in enumerate(subgroups):
            branch_fields = [f for f in subgroup.fields if not _is_control(f)]
            if branch_fields:
                latent_by_group.setdefault(gid, {})[cid] = branch_fields

    # ── Collect active fields ──────────────────────────────────────────────────
    positionals: list[LinearField] = []
    active_opts: dict[str, list[LinearField]] = {}
    ctrl_opts: dict[str, list[LinearField]] = {}

    for fld, fs in gs.state.items():
        if fs.state not in (LinearState.AVAILABLE, LinearState.ADVANCE):
            continue
        if fld.positional:
            positionals.append(fld)
            continue
        try:
            primary, aliases = _field_option_strings(fld)
        except Exception:
            continue
        if not primary:
            continue
        key = primary[0]
        if _is_control(fld):
            ctrl_opts.setdefault(key, []).append(fld)
        else:
            active_opts.setdefault(key, []).append(fld)

    # ── Entry builders ─────────────────────────────────────────────────────────

    def _opt_s(name: str) -> str:
        return f"-{name}" if len(name) == 1 else f"--{name}"

    def _entry(fields: list[LinearField]) -> dict:
        primary, aliases = _field_option_strings(fields[0])
        names = primary + aliases
        short = [n for n in names if "." not in n]
        display = sorted(short if short else names, key=lambda n: (len(n) > 1, n))
        if fields[0].field.serialized_name == tag_field:
            evs = [f.expected_value for f in fields if f.expected_value is not None]
            metavar = "{" + ",".join(evs) + "}" if evs else _type_metavar(fields[0].type)
            # Use the parent field's description (the union field), not the $class tell's doc.
            desc = (fields[0].parent.doc if fields[0].parent else None) or ""
        else:
            metavar = _type_metavar(fields[0].type)
            desc = fields[0].doc or ""
        f0 = fields[0].field
        if not f0.required:
            dflt = f0.default
            if dflt is not MISSING and dflt is not False:
                suffix = f"[default: {dflt}]"
                desc = f"{desc}  {c_dim(suffix)}".lstrip() if desc else c_dim(suffix)
        return {"names": display, "metavar": metavar, "desc": desc}

    def _render_entries(entries: list[dict], indent: str = "  ") -> list[str]:
        if not entries:
            return []
        result_lines = []
        opt_w = max(len(", ".join(_opt_s(n) for n in e["names"])) for e in entries)
        mv_w = max(len(e["metavar"]) for e in entries)
        for e in entries:
            raw = ", ".join(_opt_s(n) for n in e["names"])
            mv_pad = f"{e['metavar']:<{mv_w}}" if mv_w else ""
            mv_str = f"  {c_meta(mv_pad)}" if mv_w else ""
            result_lines.append(
                f"{indent}{c_opt(f'{raw:<{opt_w}}')}{mv_str}  {e['desc']}".rstrip()
            )
        return result_lines

    def _pos_display(fld: LinearField) -> str:
        if fld.field.serialized_name == tag_field and fld.parent is not None:
            evs = [
                f.expected_value
                for f in gs.state
                if f.field.serialized_name == tag_field
                and f.parent is fld.parent
                and f.expected_value is not None
            ]
            return ("{" + ",".join(evs) + "}") if evs else "TAG"
        return (fld.field.serialized_name or "ARG").upper()

    # ── Assemble output ────────────────────────────────────────────────────────
    out = []

    # Usage
    seen_pos_d: set[str] = set()
    pos_parts = []
    for fld in positionals:
        d = _pos_display(fld)
        if d not in seen_pos_d:
            seen_pos_d.add(d)
            pos_parts.append(c_meta(d))
    pos_str = (" " + " ".join(pos_parts)) if pos_parts else ""
    out.append(f"{c_header('Usage:')} {c_prog(prog)} {c_dim('[OPTIONS]')}{pos_str}")
    out.append("")

    # Description
    if root_type:
        doc = _class_doc(root_type)
        if doc:
            out.append(doc)
            out.append("")

    # Arguments
    unique_pos: list[tuple[str, LinearField]] = []
    seen_pos_d2: set[str] = set()
    for fld in positionals:
        d = _pos_display(fld)
        if d not in seen_pos_d2:
            seen_pos_d2.add(d)
            unique_pos.append((d, fld))
    if unique_pos:
        out.append(c_header("Arguments:"))
        w = max(len(d) for d, _ in unique_pos)
        for display, fld in unique_pos:
            out.append(f"  {c_meta(f'{display:<{w}}')}  {fld.doc or ''}".rstrip())
        out.append("")

    # Options
    opt_entries = [_entry(v) for v in active_opts.values()]
    if opt_entries:
        out.append(c_header("Options:"))
        out.extend(_render_entries(opt_entries))
        out.append("")

    # Union branches
    for gid, cid_map in latent_by_group.items():
        if not cid_map:
            continue
        group_fld = group_field_map.get(gid)
        label = (group_fld.doc if group_fld and group_fld.doc else None) or _cli_name(
            gid.split(".")[-1]
        )
        out.append(c_header(label + ":"))
        subgroups = gs._option_groups.get(gid, [])
        multi = len(cid_map) > 1
        first = True
        for cid, fields in sorted(cid_map.items()):
            if not first:
                out.append("")
            first = False
            branch_type = fields[0].enclosing_type if fields else None
            if multi and branch_type:
                letter = chr(ord("A") + cid)
                branch_doc = _class_doc(branch_type)
                branch_name = getattr(branch_type, "__name__", str(branch_type))
                out.append(f"  [{c_dim(f'Option {letter}')}] {branch_doc or branch_name}")
                indent = "    "
            else:
                indent = "  "
            branch_entries = []
            for fld in fields:
                try:
                    primary, _ = _field_option_strings(fld)
                except Exception:
                    continue
                if primary:
                    branch_entries.append(_entry([fld]))
            out.extend(_render_entries(branch_entries, indent))
        out.append("")

    # Global options
    ctrl_entries = [_entry(v) for v in ctrl_opts.values()]
    if ctrl_entries:
        out.append(c_header("Global options:"))
        out.extend(_render_entries(ctrl_entries))

    return "\n".join(out).rstrip()


@dataclass(kw_only=True)
class Control:
    # [alias: -h]
    # Show this help message and exit
    help: bool = False

    def build(self, parser, vals):
        if self.help:
            print(
                _format_help(parser.gs, parser.prog, parser.root_type, color=sys.stdout.isatty())
            )
            sys.exit(0)

        if parser.errors:
            raise ParseError._from_items(parser.errors)

        return vals


class Word:
    def __init__(self, word: str):
        self.value = word


@dataclass
class CommandLineArguments:
    """Wrapper around an argv list, consumed by :class:`FromArguments`."""

    arguments: list[str] = None
    prog: str = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = sys.argv[1:]
        if self.prog is None:
            self.prog = sys.argv[0]


class FromArguments(Medley):
    """Serieux Medley that allows deserializing any type directly from CLI args."""

    @ovld(priority=1)
    def deserialize(self, t: type[int], obj: Word, ctx: Context):
        return int(obj.value)

    @ovld(priority=1)
    def deserialize(self, t: type[float], obj: Word, ctx: Context):
        return float(obj.value)

    @ovld(priority=1)
    def deserialize(self, t: Any, obj: Word, ctx: Context):
        return recurse(t, obj.value)

    @ovld(priority=1)
    def deserialize(self, t: Any, obj: CommandLineArguments, ctx: Context):
        augmented_type = make_dataclass(
            cls_name=f"Args_{clsstring(t)}",
            bases=(),
            fields=[
                ("__value", t, field()),
                ("__control", Control, field()),
            ],
        )

        tokens = tokenize(obj.arguments)
        root_group = linearize(augmented_type)
        gs = GroupState(root_group)
        parser = Cli3Parser(
            gs, prog=obj.prog, argv=obj.arguments, deserialize=self.deserialize, root_type=t
        )
        result = parser.run(tokens)
        vals = unflatten(result, allow_lists=True)

        control = recurse(Control, vals.get("__control", {}))
        vals = control.build(parser, vals.get("__value", {}))

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
