"""
Command-line argument parser built on linearize.
Same outside interface as clargs; no argparse dependency.
"""

from __future__ import annotations

import re as _re
import sys
from collections import deque
from dataclasses import MISSING, dataclass, field
from typing import Any, Literal

from ovld import Medley, ovld, recurse
from ovld.dependent import Regexp

from ..ctx import Context
from ..exc import find_information
from ..model import ListModelizable, model
from .dotted import unflatten
from .linearize import LinearBase, LinearChoice, LinearField, LinearTagged, linearize
from .tagset import tag_field


@dataclass
class CLILocation:
    """Source location of a parsed token within an argv list."""

    argv: list[str]
    arg_index: int  # 0-based index into argv
    start: int  # inclusive char offset within argv[arg_index]
    end: int  # exclusive char offset
    prog: str = None  # program name prepended to the error display line

    def render(self, message: str, color: bool = None) -> str:
        if color is None:
            color = sys.stderr.isatty()
        offsets = []
        pos = 0
        for arg in self.argv:
            offsets.append(pos)
            pos += len(arg) + 1
        arg_line = " ".join(self.argv)
        abs_start = offsets[self.arg_index] + self.start
        abs_end = offsets[self.arg_index] + self.end
        width = max(1, abs_end - abs_start)
        err_col = "\033[1;31m" if color else ""
        reset = "\033[0m" if color else ""
        if self.prog:
            dim = "\033[2m" if color else ""
            prefix_len = len(self.prog) + 1
            line = f"{dim}{self.prog}{reset} {arg_line}"
            underline = " " * (prefix_len + abs_start) + err_col + "^" * width + reset
        else:
            line = arg_line
            underline = " " * abs_start + err_col + "^" * width + reset
        return f"{message}\n\n  {line}\n  {underline}"


class ParseError(Exception):
    def __init__(self, message: str, location: CLILocation = None):
        super().__init__(message)
        self.location = location

    def __str__(self) -> str:
        msg = self.args[0]
        if self.location is not None:
            return self.location.render(msg)
        return msg


# ── Linear item helpers ──────────────────────────────────────────────────────


def _cli_name(name: str) -> str:
    return name.replace("_", "-")


def _short(item: LinearBase) -> str:
    """Preferred short name: metadata 'option' if set, else last path component."""
    opt = item.field.metadata.get("option")
    if opt:
        return opt.lstrip("-")
    return _cli_name(item.field.name)


def _full(item: LinearBase) -> str:
    return _cli_name(item.path)


def _aliases(item: LinearBase) -> list[str]:
    alias = item.field.metadata.get("alias", [])
    if isinstance(alias, str):
        alias = [alias]
    return [a.lstrip("-") for a in alias]


def _is_positional(item: LinearBase) -> bool:
    return bool(item.field.metadata.get("positional", False))


def _is_remainder(item: LinearBase) -> bool:
    """True when positional metadata is a non-bool truthy value (e.g. '...')."""
    v = item.field.metadata.get("positional", False)
    return v not in (False, True)


def _split(items: list) -> tuple:
    """Partition linearized items into (option-style, positionals, choices)."""
    opts = [
        i for i in items if isinstance(i, (LinearField, LinearTagged)) and not _is_positional(i)
    ]
    pos = [i for i in items if isinstance(i, (LinearField, LinearTagged)) and _is_positional(i)]
    choices = [i for i in items if isinstance(i, LinearChoice)]
    return opts, pos, choices


def _dash(name: str) -> str:
    return f"-{name}" if len(name) == 1 else f"--{name}"


# ── Cli* tree ────────────────────────────────────────────────────────────────


@dataclass(kw_only=True)
class CliBase:
    """Base class for compiled CLI items."""

    field: Any  # serieux Field
    path: str  # dotted field path
    option_strings: list[str]  # [] if positional; short name first, then full path, then aliases
    positional: bool
    min_args: int  # minimum values to consume (0 for bool flags, remainder)
    max_args: int | None  # maximum values; None = unbounded
    remainder: bool  # consume ALL remaining args (including option-looking tokens)
    metavar: str  # display placeholder in help


@dataclass(kw_only=True)
class CliField(CliBase):
    """A scalar or list field."""

    type: type
    negation_strings: list[str] = field(default_factory=list)  # --no-X for bool fields


@dataclass
class CliGroup:
    """Compiled CLI items for one branch of a tagged union, with its associated type."""

    type: type
    items: list[CliBase]

    @property
    def description(self) -> str | None:
        return getattr(self.type, "__doc__", None)


@dataclass(kw_only=True)
class CliTagged(CliBase):
    """A tagged-union selector."""

    tag_options: dict[str, CliGroup]  # tag → pre-compiled branch group


@dataclass(kw_only=True)
class CliChoice(CliBase):
    """A plain (untagged) union — options drawn from all branches simultaneously."""

    choice_options: list[list[CliBase]]  # one sub-list per branch
    option_to_branches: dict[str, frozenset]  # path → frozenset of branch indices


# ── Compilation helpers ──────────────────────────────────────────────────────


def _count_short_names(items: list[LinearBase]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        s = _short(item)
        counts[s] = counts.get(s, 0) + 1
        for a in _aliases(item):
            counts[a] = counts.get(a, 0) + 1
    return counts


def _opt_strings(item: LinearBase, short_counts: dict[str, int]) -> list[str]:
    """Pre-disambiguated option strings: short name first (if unambiguous), full path, aliases."""
    s = _short(item)
    f = _full(item)
    result: list[str] = []
    if short_counts.get(s, 0) == 1 and s != f:
        result.append(s)
    result.append(f)
    result.extend(a for a in _aliases(item) if a not in result)
    return result


def _metavar_for(item: LinearField) -> str:
    if item.field.metavar:
        return item.field.metavar
    ft = item.type
    for t, mv in [(str, "TEXT"), (int, "INT"), (float, "FLOAT"), (bool, "")]:
        if ft is t:
            return mv
    return item.field.name.split(".")[-1].upper()


# ── Compilation: LinearBase → CliBase ────────────────────────────────────────


@ovld
def _to_cli(item: LinearField, short_counts: dict) -> CliBase:
    ft = item.type
    pos = _is_positional(item)
    rem = _is_remainder(item)
    mv = _metavar_for(item)
    is_list = issubclass(ft, ListModelizable)

    if pos:
        return CliField(
            field=item.field,
            path=item.path,
            option_strings=[],
            positional=True,
            min_args=0 if rem else 1,
            max_args=None if rem else 1,
            remainder=rem,
            metavar=mv,
            type=ft,
        )

    opts = _opt_strings(item, short_counts)

    if ft is bool:
        return CliField(
            field=item.field,
            path=item.path,
            option_strings=opts,
            positional=False,
            min_args=0,
            max_args=0,
            remainder=False,
            metavar="",
            type=ft,
            negation_strings=[f"no-{o}" for o in opts],
        )

    return CliField(
        field=item.field,
        path=item.path,
        option_strings=opts,
        positional=False,
        min_args=1,
        max_args=None if is_list else 1,
        remainder=False,
        metavar=mv,
        type=ft,
    )


@ovld
def _to_cli(item: LinearTagged, short_counts: dict) -> CliBase:
    pos = _is_positional(item)
    mv = "{" + ",".join(item.options.keys()) + "}"
    tag_opts = {
        tag: CliGroup(type=group.type, items=compile_cli(group.items))
        for tag, group in item.options.items()
    }

    if pos:
        return CliTagged(
            field=item.field,
            path=item.path,
            option_strings=[],
            positional=True,
            min_args=1,
            max_args=1,
            remainder=False,
            metavar=mv,
            tag_options=tag_opts,
        )

    opts = _opt_strings(item, short_counts)
    return CliTagged(
        field=item.field,
        path=item.path,
        option_strings=opts,
        positional=False,
        min_args=1,
        max_args=1,
        remainder=False,
        metavar=mv,
        tag_options=tag_opts,
    )


@ovld
def _to_cli(item: LinearChoice, short_counts: dict) -> CliBase:
    # Type-conflict check and cross-branch short-name disambiguation
    path_to_type: dict[str, type] = {}
    option_to_branches: dict[str, set] = {}
    path_seen: set[str] = set()
    cross_counts: dict[str, int] = {}

    for idx, branch in enumerate(item.options):
        branch_opts, _, _ = _split(branch)
        for b in branch_opts:
            if isinstance(b, LinearField):
                if b.path in path_to_type and path_to_type[b.path] is not b.type:
                    raise ParseError(
                        f"Option '{b.path}' has conflicting types across union branches "
                        f"({path_to_type[b.path].__name__} vs {b.type.__name__})"
                    )
                path_to_type[b.path] = b.type
                option_to_branches.setdefault(b.path, set()).add(idx)
            if b.path not in path_seen:
                path_seen.add(b.path)
                s = _short(b)
                cross_counts[s] = cross_counts.get(s, 0) + 1
                for a in _aliases(b):
                    cross_counts[a] = cross_counts.get(a, 0) + 1

    compiled = [compile_cli(branch, cross_counts) for branch in item.options]

    return CliChoice(
        field=item.field,
        path=item.path,
        option_strings=[],
        positional=False,
        min_args=0,
        max_args=0,
        remainder=False,
        metavar="",
        choice_options=compiled,
        option_to_branches={k: frozenset(v) for k, v in option_to_branches.items()},
    )


def compile_cli(items: list[LinearBase], short_counts: dict = None) -> list[CliBase]:
    """Compile LinearBase items to CliBase with pre-computed, disambiguated option strings.

    short_counts, if given, overrides auto-computed disambiguation (used for
    choice branches that share a disambiguation scope across all branches).
    """
    opts, pos_items, choices = _split(items)

    if short_counts is None:
        short_counts = _count_short_names(opts)

    result: list[CliBase] = []
    for item in opts:
        result.append(_to_cli(item, short_counts))
    for item in pos_items:
        result.append(_to_cli(item, {}))
    for item in choices:
        result.append(_to_cli(item, short_counts))
    return result


# ── Colorized help ───────────────────────────────────────────────────────────

_R = "\033[0m"
_B = "\033[1m"
_D = "\033[2m"
_CY = "\033[36m"
_YL = "\033[33m"
_GR = "\033[32m"
_MG = "\033[35m"


def _c(code: str, text: str, color: bool) -> str:
    return f"{code}{text}{_R}" if color else text


def _cli_sig(cli: CliBase, color: bool) -> str:
    """Render the option signature (name + metavar) for one cli item."""
    if cli.positional:
        return _c(_YL, cli.field.name.upper(), color)

    if not cli.option_strings:
        return ""

    visible = [s for s in cli.option_strings if "." not in s] or cli.option_strings
    names = ", ".join(_c(_CY, _dash(s), color) for s in visible)

    if isinstance(cli, CliField):
        if cli.max_args == 0:  # bool flag
            if cli.negation_strings:
                neg_name = _dash(cli.negation_strings[0])
                if cli.field.default is True:
                    # Default on: show --no-opt first so the "change" action is prominent
                    return _c(_CY, neg_name, color) + _c(
                        _D, " / " + ", ".join(_dash(s) for s in visible), color
                    )
                else:
                    return names + _c(_D, " / " + neg_name, color)
            return names
        if cli.metavar:
            names += " " + _c(_GR, cli.metavar, color)
        return names

    if isinstance(cli, CliTagged):
        return names + " " + _c(_GR, cli.metavar, color)

    return names


def _default_hint(cli: "CliField") -> str:
    """Short annotation about a field's default for help text; empty string if required."""
    f = cli.field
    if f.required:
        return ""
    d = f.default
    if d is MISSING:
        return "(optional)"
    if isinstance(d, bool):
        visible = [s for s in cli.option_strings if "." not in s] or cli.option_strings
        if d:
            flag = _dash(visible[0]) if visible else None
        else:
            flag = _dash(cli.negation_strings[0]) if cli.negation_strings else None
        return f"(default: {flag})" if flag else "(optional)"
    if isinstance(d, (int, float)):
        return f"(default: {d})"
    if isinstance(d, str) and len(d) <= 20:
        return f'(default: "{d}")'
    return "(optional)"


def _help_lines(
    items: list[CliBase], color: bool, indent: int = 0, col_width: int = 28
) -> list[str]:
    pad = "  " * indent
    lines = []
    for cli in items:
        if isinstance(cli, CliChoice):
            for branch in cli.choice_options:
                lines += _help_lines(branch, color, indent, col_width)
            continue

        sig = _cli_sig(cli, color)
        if not sig:
            continue
        raw_len = len(_re.sub(r"\033\[[0-9;]*m", "", sig))
        desc = cli.field.description or ""
        hint = _default_hint(cli) if isinstance(cli, CliField) else ""
        hint_str = _c(_D, hint, color) if hint else ""
        parts = [s for s in (desc, hint_str) if s]
        desc_str = ("  " + "  ".join(parts)) if parts else ""
        lines.append(f"{pad}{sig}{' ' * max(1, col_width - raw_len)}{desc_str}")

        if isinstance(cli, CliTagged):
            for tag, group in cli.tag_options.items():
                tag_desc = (group.description or "").strip()
                tag_label = _c(_B, tag + ":", color)
                desc_part = f"  {tag_desc}" if tag_desc else ""
                lines.append(f"{pad}  {tag_label}{desc_part}")
                lines += _help_lines(group.items, color, indent + 2, col_width)

    return lines


def _render_help(
    opts: list[CliBase],
    positionals: list[CliBase],
    description: str = "",
    color: bool = True,
    prog: str = None,
) -> str:
    parts: list[str] = []

    if prog:
        usage_opts = " [OPTIONS]" if opts else ""
        usage_pos = "".join(f" {_c(_YL, c.field.name.upper(), color)}" for c in positionals)
        parts.append(_c(_B, f"Usage: {prog}", color) + usage_opts + usage_pos)

    if description:
        parts += ["", description.strip()]

    if positionals:
        parts += ["", _c(_B, "Positional arguments:", color)]
        parts += _help_lines(positionals, color)

    if opts:
        col_width = 28
        parts += ["", _c(_B, "Options:", color)]
        help_sig = ", ".join(_c(_CY, s, color) for s in ["-h", "--help"])
        help_desc = "  Show this message and exit."
        parts.append(f"{help_sig}{' ' * max(1, col_width - len('-h, --help'))}{help_desc}")
        parts += _help_lines(opts, color, col_width=col_width)

    return "\n".join(parts)


def generate_help(
    root_type: type,
    prog: str = None,
    description: str = None,
    color: bool = None,
) -> str:
    if color is None:
        color = sys.stdout.isatty()
    cli_items = compile_cli(linearize(root_type))
    opts = [c for c in cli_items if not c.positional]
    positionals = [c for c in cli_items if c.positional]
    doc = description or getattr(root_type, "__doc__", None) or ""
    return _render_help(opts, positionals, doc, color, prog or sys.argv[0])


# ── Value conversion and field setter ────────────────────────────────────────


def _convert(ft: type, raw: str) -> Any:
    """Best-effort conversion of a raw CLI string to a Python value."""
    if ft is str:
        return raw
    if ft is int:
        try:
            return int(raw)
        except (ValueError, TypeError):
            return raw
    if ft is float:
        try:
            return float(raw)
        except (ValueError, TypeError):
            return raw
    if ft is bool:
        return raw.lower() not in ("false", "0", "no", "off")
    return raw


class ParsedDict(dict):
    """Result of _parse: a dict of field values with attached per-field source locations."""

    def __init__(self, data: dict, spans: "dict[str, CLILocation]", argv: list[str]) -> None:
        super().__init__(data)
        self.spans = spans  # flat dotted-path → CLILocation
        self.argv = argv


# ── Choice state tracker ─────────────────────────────────────────────────────


@dataclass
class ChoiceState:
    """Tracks which branches of a CliChoice remain consistent as options are parsed."""

    cli: CliChoice
    possible: set = field(default_factory=set)

    def __post_init__(self):
        self.possible = set(range(len(self.cli.choice_options)))

    def observe(self, path: str) -> None:
        if path in self.cli.option_to_branches:
            self.possible &= self.cli.option_to_branches[path]


# ── Actions ──────────────────────────────────────────────────────────────────


@dataclass
class Action:
    """Base for option actions; one instance per option string in ParserState.options."""

    cli: CliBase

    def activate(self, state: "ParserState") -> bool:
        """Activate the action. Returns True if inline was consumed, False if not."""
        raise NotImplementedError  # pragma: no cover


@dataclass
class SetFlag(Action):
    """Set a bool field to a fixed value without consuming any argument."""

    value: bool

    def activate(self, state) -> bool:
        state.result[self.cli.path] = self.value
        state.spans[self.cli.path] = state.key_loc
        state.observe(self.cli.path)
        return False


@dataclass
class SetValue(Action):
    """Consume the next argument and set a scalar/list field."""

    def activate(self, state) -> bool:
        value, loc = state.consume()
        state.set_field(self.cli, value, loc)
        return True


@dataclass
class ActivateTag(Action):
    """Consume the next argument as a tag name and activate the matching union branch."""

    def activate(self, state) -> bool:
        value, loc = state.consume()
        state.activate_tagged(self.cli, value, loc)
        state.seen.append(value)
        state.observe(self.cli.path)
        return True


# ── Core parser ──────────────────────────────────────────────────────────────


@dataclass
class _Token:
    """One unit in the parse queue, with a link back to its source in argv."""

    text: str
    arg_index: int  # index into argv
    src_offset: int  # offset of text[0] within argv[arg_index]


class ParserState:
    """Mutable state for a single _parse run."""

    def __init__(
        self,
        root_type: type,
        argv: list[str],
        description: str = None,
        prog: str = None,
    ) -> None:
        self.argv = argv
        self.prog = prog or sys.argv[0]
        self.description = description or getattr(root_type, "__doc__", None)
        self.options: dict[str, Action] = {}
        self.pos_queue: list[CliBase] = []
        self.states: list[ChoiceState] = []
        self.active: list[CliBase] = []
        self.choice_branch_paths: set[str] = set()
        self.result: dict[str, Any] = {}
        self.spans: dict[str, CLILocation] = {}
        self.seen: list[str] = []
        self.queue: deque[_Token] = deque(_Token(t, i, 0) for i, t in enumerate(argv))
        # transient per-token context set by _process before calling action.activate
        self.key_loc: CLILocation | None = None
        self.inline: str | None = None
        self.val_loc: CLILocation | None = None

        for cli in compile_cli(linearize(root_type)):
            if cli.positional:
                self.pos_queue.append(cli)
            elif isinstance(cli, CliChoice):
                for branch in cli.choice_options:
                    for b_item in branch:
                        self.register(b_item, priority=False, add_to_active=False)
                        self.choice_branch_paths.add(b_item.path)
                self.states.append(ChoiceState(cli))
                self.active.append(cli)
            else:
                self.register(cli)

    def show_help(self) -> None:
        seen_str = " ".join(self.seen)
        display_prog = sys.argv[0] + (f" {seen_str}" if seen_str else "")
        print(
            _render_help(
                [c for c in self.active if not c.positional],
                list(self.pos_queue),
                description=self.description,
                color=sys.stdout.isatty(),
                prog=display_prog,
            )
        )
        sys.exit(0)

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, cli: CliBase, priority: bool = True, add_to_active: bool = True) -> None:
        if isinstance(cli, CliTagged):
            action: Action = ActivateTag(cli=cli)
        elif isinstance(cli, CliField) and cli.max_args == 0:
            for s in cli.negation_strings:
                if priority or s not in self.options:
                    self.options[s] = SetFlag(cli=cli, value=False)
            action = SetFlag(cli=cli, value=True)
        else:
            action = SetValue(cli=cli)
        for s in cli.option_strings:
            if priority or s not in self.options:
                self.options[s] = action
        if add_to_active and id(cli) not in {id(x) for x in self.active}:
            self.active.append(cli)

    def observe(self, path: str) -> None:
        for state in self.states:
            state.observe(path)

    def activate_tagged(self, tagged: CliTagged, tag: str, tag_loc: CLILocation = None) -> None:
        if tag not in tagged.tag_options:
            raise ParseError(
                f"Unknown tag {tag!r} for '{tagged.path}'. Valid tags: {list(tagged.tag_options)}",
                tag_loc,
            )
        group = tagged.tag_options[tag]
        if group.description:
            self.description = group.description.strip()
        path = f"{tagged.path}.{tag_field}"
        self.result[path] = tag
        if tag_loc is not None:
            self.spans[path] = tag_loc
        for s in [s for s, a in self.options.items() if a.cli is tagged]:
            del self.options[s]
        if tagged in self.active:
            self.active.remove(tagged)
        for cli in group.items:
            if cli.positional:
                self.pos_queue.insert(0, cli)
            else:
                self.register(cli)

    # ── Location ──────────────────────────────────────────────────────────────

    def _loc(self, tok: _Token, start: int, end: int) -> CLILocation:
        return CLILocation(
            argv=self.argv,
            arg_index=tok.arg_index,
            start=tok.src_offset + start,
            end=tok.src_offset + end,
            prog=self.prog,
        )

    # ── Token processing ──────────────────────────────────────────────────────

    def consume(self, *, consume_options: bool = True) -> tuple[str, CLILocation]:
        """Return (value, loc), consuming the next queued token if no inline value."""
        if self.inline is not None:
            return self.inline, self.val_loc
        if not self.queue:
            raise ParseError("Expected a value", self.key_loc)
        nxt = self.queue[0]
        if not consume_options and nxt.text.startswith("-"):
            raise ParseError("Expected a value", self.key_loc)
        self.queue.popleft()
        return nxt.text, self._loc(nxt, 0, len(nxt.text))

    def set_field(self, cli: CliField, value_str: str, loc: CLILocation = None) -> None:
        ft = cli.type
        if issubclass(ft, ListModelizable) or cli.field.metadata.get("action") == "append":
            m = model(ft)
            elem_ft = m.element_field.type if (m and m.element_field) else str
            converted = _convert(elem_ft, value_str)
            existing = self.result.get(cli.path, [])
            self.result[cli.path] = (existing if isinstance(existing, list) else [existing]) + [
                converted
            ]
        else:
            self.result[cli.path] = _convert(ft, value_str)
        if loc is not None:
            self.spans[cli.path] = loc
        self.observe(cli.path)

    @ovld(priority=1)
    def _process(self, tok: _Token, text: Literal["-h", "--help"]):
        self.show_help()

    @ovld
    def _process(self, tok: _Token, text: Regexp["^--"]):
        """Handle --key and --key=val."""
        key = tok.text[2:]
        self.inline, self.val_loc = None, None
        if "=" in key:
            key, self.inline = key.split("=", 1)
            self.val_loc = self._loc(tok, 2 + len(key) + 1, len(tok.text))
        self.key_loc = self._loc(tok, 0, 2 + len(key))
        if key not in self.options:
            raise ParseError(f"Unknown option: {tok.text!r}", self._loc(tok, 0, len(tok.text)))
        self.options[key].activate(self)

    @ovld
    def _process(self, tok: _Token, text: Regexp["^-[^-]"]):
        """Handle -x, -xyz, -x=val, -xval.

        Processes the first flag char and pushes the remainder back as a new
        token so the main loop handles it naturally on the next iteration.
        """
        ch, rest = tok.text[1], tok.text[2:]
        self.key_loc = self._loc(tok, 1, 2)
        if ch not in self.options:
            raise ParseError(f"Unknown option: -{ch!r}", self.key_loc)
        action = self.options[ch]
        eq = rest.startswith("=")
        self.inline = rest[eq:] or None
        self.val_loc = self._loc(tok, 2 + eq, 2 + eq + len(self.inline)) if self.inline else None
        if not action.activate(self) and rest:
            self.queue.appendleft(_Token(f"-{rest}", tok.arg_index, tok.src_offset + 1))

    @ovld
    def _process(self, tok: _Token, text: str):
        if not self.pos_queue:
            raise ParseError(
                f"Unexpected positional argument: {tok.text!r}",
                self._loc(tok, 0, len(tok.text)),
            )
        cli = self.pos_queue[0]
        loc = self._loc(tok, 0, len(tok.text))
        if isinstance(cli, CliTagged):
            self.pos_queue.pop(0)
            self.activate_tagged(cli, tok.text, loc)
            self.seen.append(tok.text)
            self.observe(cli.path)
        else:
            self.set_field(cli, tok.text, loc)
            if not cli.remainder:
                self.pos_queue.pop(0)

    def step(self) -> None:
        tok = self.queue.popleft()

        if self.pos_queue and self.pos_queue[0].remainder:
            self.set_field(self.pos_queue[0], tok.text, self._loc(tok, 0, len(tok.text)))
            return

        self._process(tok, tok.text)

    # ── Post-parse validation ─────────────────────────────────────────────────

    def check_missing(self) -> None:
        seen_paths: set[str] = set()
        missing: list[CliBase] = []
        for action in self.options.values():
            cli = action.cli
            if cli.path in seen_paths or cli.path in self.choice_branch_paths:
                continue
            seen_paths.add(cli.path)
            if not cli.field.required:
                continue
            key = f"{cli.path}.{tag_field}" if isinstance(cli, CliTagged) else cli.path
            if key not in self.result:
                missing.append(cli)
        for cli in self.pos_queue:
            if not cli.remainder and cli.field.required:
                missing.append(cli)
        if not missing:
            return
        names = []
        for cli in missing:
            if cli.positional:
                names.append(cli.metavar or cli.field.name.upper())
            else:
                visible = [_dash(s) for s in cli.option_strings if "." not in s]
                names.append(visible[0] if visible else _dash(_full(cli)))
        noun = "arguments" if len(names) > 1 else "argument"
        raise ParseError(f"Missing required {noun}: {', '.join(names)}")


def _parse(
    root_type: type, argv: list[str], description: str = None, prog: str = None
) -> ParsedDict:
    state = ParserState(root_type, argv, description, prog)
    while state.queue:
        state.step()
    state.check_missing()
    return ParsedDict(unflatten(state.result), state.spans, argv)


# ── Public interface ─────────────────────────────────────────────────────────


@dataclass
class CommandLineArguments:
    arguments: list[str]
    mapping: dict[str, str | dict[str, Any]] = field(default_factory=lambda: {"": {"auto": True}})

    def parse(self, root_type: type, argv: list[str]):
        return parse_cli(root_type=root_type, mapping=self.mapping, argv=argv)


@dataclass
class CLIDefinition:
    root_type: type = None
    mapping: dict[str, str | dict[str, Any]] = field(default_factory=lambda: {"": {"auto": True}})
    description: str = None
    prog: str = None

    def __call__(self, argv: list[str]):
        return _parse(self.root_type, argv, description=self.description, prog=self.prog)


def parse_cli(
    root_type: type,
    argv: list[str] = None,
    mapping=None,
    description: str = None,
    prog: str = None,
):
    mapping = {"": {"auto": True}} if mapping is None else mapping
    argv = sys.argv[1:] if argv is None else argv
    return CLIDefinition(root_type=root_type, mapping=mapping, description=description, prog=prog)(
        argv
    )


class FromArguments(Medley):
    @ovld(priority=1)
    def deserialize(self, t: Any, obj: CommandLineArguments, ctx: Context):
        vals = obj.parse(t, obj.arguments)
        try:
            return recurse(t, vals, ctx)
        except Exception as exc:
            if isinstance(vals, ParsedDict):
                info = find_information(exc=exc, ctx=ctx)
                path = ".".join(str(p) for p in info.path)
                if loc := vals.spans.get(path):
                    raise ParseError(str(exc), loc) from None
            raise
