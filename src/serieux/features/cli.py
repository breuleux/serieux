"""
Command-line argument parser built on linearize.
Same outside interface as clargs; no argparse dependency.
"""

from __future__ import annotations

import re as _re
import sys
from dataclasses import dataclass, field
from typing import Any

from ovld import Medley, ovld, recurse

from ..ctx import Context
from ..model import ListModelizable, model
from .dotted import unflatten
from .linearize import LinearBase, LinearChoice, LinearField, LinearTagged, linearize
from .tagset import tag_field


class ParseError(Exception):
    pass


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
    opts = [i for i in items if isinstance(i, (LinearField, LinearTagged)) and not _is_positional(i)]
    pos  = [i for i in items if isinstance(i, (LinearField, LinearTagged)) and _is_positional(i)]
    choices = [i for i in items if isinstance(i, LinearChoice)]
    return opts, pos, choices


def _dash(name: str) -> str:
    return f"-{name}" if len(name) == 1 else f"--{name}"


# ── Cli* tree ────────────────────────────────────────────────────────────────


@dataclass(kw_only=True)
class CliBase:
    """Base class for compiled CLI items."""
    field: Any          # serieux Field
    path: str           # dotted field path
    option_strings: list[str]   # [] if positional; short name first, then full path, then aliases
    positional: bool
    min_args: int       # minimum values to consume (0 for bool flags, remainder)
    max_args: int | None  # maximum values; None = unbounded
    remainder: bool     # consume ALL remaining args (including option-looking tokens)
    metavar: str        # display placeholder in help


@dataclass(kw_only=True)
class CliField(CliBase):
    """A scalar or list field."""
    type: type
    negation_strings: list[str] = field(default_factory=list)  # --no-X for bool fields


@dataclass(kw_only=True)
class CliTagged(CliBase):
    """A tagged-union selector."""
    tag_options: dict[str, list[CliBase]]  # tag → pre-compiled branch items


@dataclass(kw_only=True)
class CliChoice(CliBase):
    """A plain (untagged) union — options drawn from all branches simultaneously."""
    choice_options: list[list[CliBase]]         # one sub-list per branch
    option_to_branches: dict[str, frozenset]    # path → frozenset of branch indices


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
            field=item.field, path=item.path,
            option_strings=[], positional=True,
            min_args=0 if rem else 1,
            max_args=None if rem else 1,
            remainder=rem, metavar=mv,
            type=ft,
        )

    opts = _opt_strings(item, short_counts)

    if ft is bool:
        return CliField(
            field=item.field, path=item.path,
            option_strings=opts, positional=False,
            min_args=0, max_args=0,
            remainder=False, metavar="",
            type=ft,
            negation_strings=[f"no-{o}" for o in opts],
        )

    return CliField(
        field=item.field, path=item.path,
        option_strings=opts, positional=False,
        min_args=1, max_args=None if is_list else 1,
        remainder=False, metavar=mv,
        type=ft,
    )


@ovld
def _to_cli(item: LinearTagged, short_counts: dict) -> CliBase:
    pos = _is_positional(item)
    mv = "{" + ",".join(item.options.keys()) + "}"
    tag_opts = {tag: compile_cli(branch) for tag, branch in item.options.items()}

    if pos:
        return CliTagged(
            field=item.field, path=item.path,
            option_strings=[], positional=True,
            min_args=1, max_args=1, remainder=False, metavar=mv,
            tag_options=tag_opts,
        )

    opts = _opt_strings(item, short_counts)
    return CliTagged(
        field=item.field, path=item.path,
        option_strings=opts, positional=False,
        min_args=1, max_args=1, remainder=False, metavar=mv,
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
        field=item.field, path=item.path,
        option_strings=[], positional=False,
        min_args=0, max_args=0, remainder=False, metavar="",
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

_R  = "\033[0m"
_B  = "\033[1m"
_D  = "\033[2m"
_CY = "\033[36m"
_YL = "\033[33m"
_GR = "\033[32m"
_MG = "\033[35m"


def _c(code: str, text: str, color: bool) -> str:
    return f"{code}{text}{_R}" if color else text


def _cli_sig(cli: CliBase, color: bool) -> str:
    """Render the option signature (name + metavar) for one cli item."""
    if cli.positional:
        return _c(_MG, cli.field.name.upper(), color)

    if not cli.option_strings:
        return ""

    visible = [s for s in cli.option_strings if "." not in s] or cli.option_strings
    names = ", ".join(_c(_CY, _dash(s), color) for s in visible)

    if isinstance(cli, CliField):
        if cli.max_args == 0:  # bool flag — show first negation after a slash
            neg = _c(_D, " / " + _dash(cli.negation_strings[0]), color) if cli.negation_strings else ""
            return names + neg
        if cli.metavar:
            names += " " + _c(_GR, cli.metavar, color)
        return names

    if isinstance(cli, CliTagged):
        return names + " " + _c(_GR, cli.metavar, color)

    return names


def _help_lines(items: list[CliBase], color: bool, indent: int = 0, col_width: int = 28) -> list[str]:
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
        desc_str = ("  " + desc) if desc else ""
        lines.append(f"{pad}{sig}{' ' * max(1, col_width - raw_len)}{desc_str}")

        if isinstance(cli, CliTagged):
            for tag, branch_items in cli.tag_options.items():
                lines.append(f"{pad}  {_c(_YL, tag + ':', color)}")
                lines += _help_lines(branch_items, color, indent + 2, col_width)

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
        usage_pos = "".join(f" {_c(_MG, c.field.name.upper(), color)}" for c in positionals)
        parts.append(_c(_B, f"Usage: {prog}", color) + usage_opts + usage_pos)

    if description:
        parts += ["", description.strip()]

    if positionals:
        parts += ["", _c(_YL + _B, "Positional arguments:", color)]
        parts += _help_lines(positionals, color)

    if opts:
        col_width = 28
        parts += ["", _c(_YL + _B, "Options:", color)]
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


def _set_field(cli: CliField, value_str: str, result: dict, observe) -> None:
    ft = cli.type
    if issubclass(ft, ListModelizable) or cli.field.metadata.get("action") == "append":
        m = model(ft)
        elem_ft = m.element_field.type if (m and m.element_field) else str
        converted = _convert(elem_ft, value_str)
        existing = result.get(cli.path, [])
        result[cli.path] = (existing if isinstance(existing, list) else [existing]) + [converted]
    else:
        result[cli.path] = _convert(ft, value_str)
    observe(cli.path)


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


# ── Core parser ──────────────────────────────────────────────────────────────


def _parse(root_type: type, argv: list[str], description: str = None) -> dict:
    cli_items = compile_cli(linearize(root_type))

    options: dict[str, CliBase] = {}
    neg_options: dict[str, CliField] = {}
    pos_queue: list[CliBase] = []
    states: list[ChoiceState] = []
    active: list[CliBase] = []     # ordered list for contextual help display

    def register(cli: CliBase, priority: bool = True) -> None:
        for s in cli.option_strings:
            if priority or s not in options:
                options[s] = cli
        if isinstance(cli, CliField):
            for s in cli.negation_strings:
                if priority or s not in neg_options:
                    neg_options[s] = cli
        if id(cli) not in {id(x) for x in active}:
            active.append(cli)

    for cli in cli_items:
        if cli.positional:
            pos_queue.append(cli)
        elif isinstance(cli, CliChoice):
            for branch in cli.choice_options:
                for b_item in branch:
                    register(b_item, priority=False)
            states.append(ChoiceState(cli))
            active.append(cli)
        else:
            register(cli, priority=True)

    result: dict[str, Any] = {}

    def observe(path: str) -> None:
        for state in states:
            state.observe(path)

    def activate_tagged(tagged: CliTagged, tag: str) -> None:
        if tag not in tagged.tag_options:
            raise ParseError(
                f"Unknown tag {tag!r} for '{tagged.path}'. Valid tags: {list(tagged.tag_options)}"
            )
        result[f"{tagged.path}.{tag_field}"] = tag
        # Remove the resolved selector from the registry and active list.
        for s in [s for s, v in options.items() if v is tagged]:
            del options[s]
        if tagged in active:
            active.remove(tagged)
        # Register branch items with priority (they override any existing short names).
        for cli in tagged.tag_options[tag]:
            if cli.positional:
                pos_queue.insert(0, cli)
            else:
                register(cli, priority=True)

    seen: list[str] = []   # positional tokens consumed so far, for the usage line

    i = 0
    while i < len(argv):
        token = argv[i]

        # Remainder mode: current positional gobbles everything, including --flags.
        if pos_queue and pos_queue[0].remainder:
            _set_field(pos_queue[0], token, result, observe)
            i += 1
            continue

        if token in ("-h", "--help"):
            opts_display = [c for c in active if not c.positional]
            seen_str = " ".join(seen)
            prog = sys.argv[0] + (f" {seen_str}" if seen_str else "")
            print(_render_help(opts_display, list(pos_queue), description=description, color=sys.stdout.isatty(), prog=prog))
            sys.exit(0)

        elif token.startswith("--") or (token.startswith("-") and len(token) == 2):
            key = token[1:] if len(token) == 2 else token[2:]

            if key in neg_options:
                cli = neg_options[key]
                result[cli.path] = False
                observe(cli.path)
                i += 1
                continue

            if key not in options:
                raise ParseError(f"Unknown option: {token!r}")

            cli = options[key]

            if isinstance(cli, CliTagged):
                if i + 1 >= len(argv):
                    raise ParseError(f"Expected tag value after {token!r}")
                activate_tagged(cli, argv[i + 1])
                seen.append(argv[i + 1])
                observe(cli.path)
                i += 2

            elif cli.max_args == 0:  # bool flag
                result[cli.path] = True
                observe(cli.path)
                i += 1

            else:
                if i + 1 >= len(argv):
                    raise ParseError(f"Expected value after {token!r}")
                _set_field(cli, argv[i + 1], result, observe)
                i += 2

        elif token.startswith("-") and len(token) > 2 and not token.startswith("--"):
            # Compact single-dash flags: -xyz
            rest = token[1:]
            while rest:
                ch = rest[0]
                rest = rest[1:]
                if ch in neg_options:
                    cli = neg_options[ch]
                    result[cli.path] = False
                    observe(cli.path)
                elif ch in options:
                    cli = options[ch]
                    if cli.max_args == 0:  # bool
                        result[cli.path] = True
                        observe(cli.path)
                    else:
                        if not rest:
                            i += 1
                            if i >= len(argv):
                                raise ParseError(f"Expected value after -{ch!r}")
                            rest = argv[i]
                        _set_field(cli, rest, result, observe)
                        rest = ""
                else:
                    raise ParseError(f"Unknown option: -{ch!r}")
            i += 1

        else:
            if not pos_queue:
                raise ParseError(f"Unexpected positional argument: {token!r}")
            cli = pos_queue[0]

            if isinstance(cli, CliTagged):
                pos_queue.pop(0)
                activate_tagged(cli, token)
                seen.append(token)
                observe(cli.path)
            else:
                _set_field(cli, token, result, observe)
                if not cli.remainder:
                    pos_queue.pop(0)
            i += 1

    return unflatten(result)


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

    def __call__(self, argv: list[str]):
        return _parse(self.root_type, argv, description=self.description)


def parse_cli(root_type: type, argv: list[str] = None, mapping=None, description: str = None):
    mapping = {"": {"auto": True}} if mapping is None else mapping
    argv = sys.argv[1:] if argv is None else argv
    return CLIDefinition(root_type=root_type, mapping=mapping, description=description)(argv)


class FromArguments(Medley):
    @ovld(priority=1)
    def deserialize(self, t: Any, obj: CommandLineArguments, ctx: Context):
        vals = obj.parse(t, obj.arguments)
        return recurse(t, vals, ctx)
