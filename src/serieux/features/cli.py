"""
Command-line argument parser built on linearize.
Same outside interface as clargs; no argparse dependency.
"""

from __future__ import annotations

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


# ── option name helpers ──────────────────────────────────────────────────────


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


# ── registry ─────────────────────────────────────────────────────────────────


def _split(items):
    """Partition linearized items into (option-style, positionals, choices)."""
    opts = [
        i for i in items if isinstance(i, (LinearField, LinearTagged)) and not _is_positional(i)
    ]
    pos = [i for i in items if isinstance(i, (LinearField, LinearTagged)) and _is_positional(i)]
    choices = [i for i in items if isinstance(i, LinearChoice)]
    return opts, pos, choices


@dataclass
class ChoiceTracker:
    """Tracks which branches of a LinearChoice remain consistent as options are parsed."""

    choice: LinearChoice
    # full option path → frozenset of branch indices that contain it
    option_to_branches: dict[str, frozenset]
    possible: set  # branch indices still consistent with observed options

    def observe(self, path: str) -> None:
        """Narrow possible branches when an option at *path* is seen."""
        if path in self.option_to_branches:
            self.possible &= self.option_to_branches[path]


def _build_choice_tracker(choice: LinearChoice, options: dict) -> ChoiceTracker:
    """Register all branch options (no priority) and return a ChoiceTracker.

    Raises ParseError if the same option name appears in two branches with
    different types, as it would be impossible to discriminate.
    """
    path_to_type: dict[str, type] = {}
    option_to_branches: dict[str, set] = {}

    for i, branch in enumerate(choice.options):
        branch_opts, _, _ = _split(branch)
        for item in branch_opts:
            if isinstance(item, LinearField):
                if item.path in path_to_type and path_to_type[item.path] is not item.type:
                    raise ParseError(
                        f"Option '{item.path}' has conflicting types across union branches "
                        f"({path_to_type[item.path].__name__} vs {item.type.__name__})"
                    )
                path_to_type[item.path] = item.type
                option_to_branches.setdefault(item.path, set()).add(i)
        _register(branch_opts, options, priority=False)

    return ChoiceTracker(
        choice=choice,
        option_to_branches={k: frozenset(v) for k, v in option_to_branches.items()},
        possible=set(range(len(choice.options))),
    )


def _register(items, options: dict, priority: bool = False) -> None:
    """Register option-style items into *options* (mutated in place).

    Short name conflicts within *items* cause both entries to fall back to
    their full path only.  When priority=True new short names always win,
    overriding any previous entry (used after a LinearTagged branch is
    selected).
    """
    short_count: dict[str, int] = {}
    for item in items:
        s = _short(item)
        short_count[s] = short_count.get(s, 0) + 1
        for a in _aliases(item):
            short_count[a] = short_count.get(a, 0) + 1

    for item in items:
        # Full path is unconditional.
        options[_full(item)] = item

        s = _short(item)
        if short_count[s] == 1 and (priority or s not in options):
            options[s] = item

        for a in _aliases(item):
            if priority or a not in options:
                options[a] = item

        # Bool fields: also register --no-<name> variants.
        if isinstance(item, LinearField) and item.type is bool:
            no_full = "no-" + _full(item)
            options[no_full] = (item, False)
            no_s = "no-" + s
            if short_count[s] == 1 and (priority or no_s not in options):
                options[no_s] = (item, False)


# ── value conversion ─────────────────────────────────────────────────────────


def _convert(ft: type, raw: str) -> Any:
    """Best-effort conversion of a raw CLI string to a Python value.

    Complex types (StringModelizable, Enum, …) are left as strings so that
    serieux's own deserializer handles them.
    """
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


# ── field-value setter ───────────────────────────────────────────────────────


def _set_field(entry: LinearField, value_str: str, result: dict, observe_all) -> None:
    ft = entry.type
    if issubclass(ft, ListModelizable) or entry.field.metadata.get("action") == "append":
        m = model(ft)
        elem_ft = m.element_field.type if (m and m.element_field) else str
        converted = _convert(elem_ft, value_str)
        existing = result.get(entry.path, [])
        result[entry.path] = (existing if isinstance(existing, list) else [existing]) + [converted]
    else:
        result[entry.path] = _convert(ft, value_str)
    observe_all(entry.path)


# ── core parser ──────────────────────────────────────────────────────────────


def _parse(root_type: type, argv: list[str]) -> dict:
    items = linearize(root_type)
    opt_items, pos_items, choice_items = _split(items)

    options: dict[str, LinearBase | tuple] = {}
    _register(opt_items, options, priority=False)
    pos_queue: list[LinearBase] = list(pos_items)
    trackers: list[ChoiceTracker] = [_build_choice_tracker(c, options) for c in choice_items]

    result: dict[str, Any] = {}

    def observe_all(path: str) -> None:
        for tracker in trackers:
            tracker.observe(path)

    def activate_tagged(tagged: LinearTagged, tag: str) -> None:
        if tag not in tagged.options:
            raise ParseError(
                f"Unknown tag {tag!r} for '{tagged.path}'. Valid tags: {list(tagged.options)}"
            )
        result[f"{tagged.path}.{tag_field}"] = tag
        branch_opts, branch_pos, branch_choices = _split(tagged.options[tag])
        _register(branch_opts, options, priority=True)
        pos_queue[:0] = branch_pos  # new positionals take precedence

    i = 0
    while i < len(argv):
        token = argv[i]

        if token.startswith("--") or (token.startswith("-") and len(token) == 2):
            key = token[1:] if len(token) == 2 else token[2:]
            if key not in options:
                raise ParseError(f"Unknown option: {token!r}")

            entry = options[key]

            # Bool negation: stored as (item, False)
            if isinstance(entry, tuple):
                item, value = entry
                result[item.path] = value
                observe_all(item.path)
                i += 1
                continue

            if isinstance(entry, LinearTagged):
                if i + 1 >= len(argv):
                    raise ParseError(f"Expected tag value after {token!r}")
                activate_tagged(entry, argv[i + 1])
                observe_all(entry.path)
                i += 2

            elif entry.type is bool:
                result[entry.path] = True
                observe_all(entry.path)
                i += 1

            else:
                if i + 1 >= len(argv):
                    raise ParseError(f"Expected value after {token!r}")
                _set_field(entry, argv[i + 1], result, observe_all)
                i += 2

        elif token.startswith("-") and len(token) > 2:
            # Compact single-dash flags: -xyz
            # If -x is bool: set x=True and continue with -yz.
            # If -x is non-bool: yz is x's value.
            rest = token[1:]
            while rest:
                ch = rest[0]
                rest = rest[1:]
                if ch not in options:
                    raise ParseError(f"Unknown option: -{ch!r}")
                entry = options[ch]
                if isinstance(entry, tuple):  # bool negation
                    item, value = entry
                    result[item.path] = value
                    observe_all(item.path)
                elif isinstance(entry, LinearField) and entry.type is bool:
                    result[entry.path] = True
                    observe_all(entry.path)
                else:
                    # Non-bool: remaining chars are the value, or next token if none left
                    if not rest:
                        i += 1
                        if i >= len(argv):
                            raise ParseError(f"Expected value after -{ch!r}")
                        rest = argv[i]
                    _set_field(entry, rest, result, observe_all)
                    rest = ""
            i += 1

        else:
            # Positional token
            if not pos_queue:
                raise ParseError(f"Unexpected positional argument: {token!r}")
            item = pos_queue.pop(0)

            if isinstance(item, LinearTagged):
                activate_tagged(item, token)
                observe_all(item.path)
            else:
                result[item.path] = _convert(item.type, token)
                observe_all(item.path)
            i += 1

    return unflatten(result)


# ── public interface ─────────────────────────────────────────────────────────


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
        return _parse(self.root_type, argv)


def parse_cli(root_type: type, argv: list[str] = None, mapping=None, description: str = None):
    mapping = {"": {"auto": True}} if mapping is None else mapping
    argv = sys.argv[1:] if argv is None else argv
    return CLIDefinition(root_type=root_type, mapping=mapping, description=description)(argv)


class FromArguments(Medley):
    @ovld(priority=1)
    def deserialize(self, t: Any, obj: CommandLineArguments, ctx: Context):
        vals = obj.parse(t, obj.arguments)
        return recurse(t, vals, ctx)
