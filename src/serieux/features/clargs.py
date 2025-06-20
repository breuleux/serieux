import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from types import NoneType
from typing import Any, get_args

from ovld import Medley, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import strip_all
from ..model import Field, FieldModelizable, StringModelizable, field_at, model
from ..utils import IsLiteral, UnionAlias, clsstring
from .dotted import unflatten
from .partial import Sources
from .tagged import Tagged

##################
# Implementation #
##################


def _compose(dest, new_part):
    return f"{dest}.{new_part}" if dest else new_part


def _soft_conversion(t):
    def filter(x):
        try:
            return t(x)
        except (ValueError, TypeError):
            return x

    return filter


@dataclass
class CommandLineArguments:
    arguments: list[str]
    mapping: dict[str, str | dict[str, Any]] = field(default_factory=lambda: {"": {"auto": True}})

    def parse(self, root_type, argv):
        return parse_cli(root_type=root_type, mapping=self.mapping, argv=argv)


class ConcatenateAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, " ".join(values) if isinstance(values, list) else values)


class ParseStringAction(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        if isinstance(value, str) and re.fullmatch(string=value, pattern=r"[\[\{].*[\}\]]"):
            value = json.loads(value)
        setattr(namespace, self.dest, value)


@ovld
def make_argument(t: type[str], partial: dict, model_field: Field):
    rval = {**partial, "type": t}
    if "nargs" in partial and "action" not in partial:
        rval["action"] = ConcatenateAction
    return rval


@ovld
def make_argument(t: type[int] | type[float], partial: dict, model_field: Field):
    return {**partial, "type": _soft_conversion(t)}


@ovld
def make_argument(t: type[bool], partial: dict, model_field: Field):
    partial.pop("metavar", None)
    partial.pop("type", None)
    return {**partial, "action": argparse.BooleanOptionalAction}


@ovld
def make_argument(t: type[list], partial: dict, model_field: Field):
    (lt,) = get_args(t) or (object,)
    if partial.get("action", None) == "append":
        return {"type": lt, **partial}
    else:
        return {"nargs": "*", "type": _soft_conversion(lt), **partial}


@ovld(priority=1)
def make_argument(t: type[Enum], partial: dict, model_field: Field):
    return {**partial, "type": str, "choices": [e.value for e in t]}


@ovld
def make_argument(t: type[IsLiteral], partial: dict, model_field: Field):
    return {**partial, "type": str, "choices": [x for x in t.__args__]}


def regex_checker(pattern, descr):
    def check(value):
        if not re.fullmatch(pattern, value):
            msg = (
                f"is invalid. It must be: {descr}"
                if descr
                else f"does not match pattern {pattern!r}"
            )
            raise argparse.ArgumentError(None, f"Value {value!r} {msg}")
        return value

    return check


@ovld
def make_argument(t: type[StringModelizable], partial: dict, model_field: Field):
    m = model(t)
    return {**partial, "type": regex_checker(m.regexp, m.string_description) if m.regexp else str}


@ovld
def make_argument(t: type[object], partial: dict, model_field: Field):
    return {**partial, "action": ParseStringAction}


@ovld
def make_argument(t: type[Tagged], partial: dict, model_field: Field):
    return "subparser"


@ovld
def make_argument(t: type[UnionAlias], partial: dict, model_field: Field):
    if any(issubclass(o, (FieldModelizable, Tagged)) for o in get_args(t)):
        return "subparser"
    else:
        options = [o for o in get_args(t) if o is not NoneType]
        if len(options) == 1:
            return recurse(options[0], partial, model_field)
        else:  # pragma: no cover
            raise TypeError("Unions of primitive/non-Modelizable types are not supported yet")


_add_argument_argnames = [
    "action",
    "nargs",
    "const",
    "default",
    "type",
    "choices",
    "required",
    "help",
    "metavar",
    "dest",
    "version",
    "alias",
    "option",
    "positional",
]


def add_argument_from_field(parser, fdest, overrides, field: Field):
    name = field.name.replace("_", "-")
    typ = strip_all(field.type)
    meta = {k: v for k, v in field.metadata.items() if k in _add_argument_argnames}
    overrides = dict(overrides)
    positional = meta.pop("positional", False) or overrides.pop("positional", False)
    fhelp = field.description or field.name
    mvar = name.split(".")[-1].upper()

    if positional:
        args = {"__args__": [fdest], "help": fhelp, "metavar": mvar, **overrides}
        args["nargs"] = "?" if not field.required else 1
    else:
        args = {
            "__args__": [f"--{name}" if len(name) > 1 else f"-{name}"],
            "help": fhelp,
            "metavar": mvar,
            "required": field.required,
            "dest": fdest,
            **meta,
            **overrides,
        }

    args = make_argument(typ, args, field)
    if args == "subparser":
        add_arguments(typ, parser, fdest, overrides.get("required", None) is False)
    else:
        pos = args.pop("__args__")
        if opt := args.pop("option", None):
            if not isinstance(opt, list):
                opt = [opt]
            pos[:] = opt
        if alias := args.pop("alias", None):
            if not isinstance(alias, list):
                alias = [alias]
            pos.extend([a for a in alias if a not in pos])
        parser.add_argument(*pos, **args)


@ovld
def add_arguments(
    t: type[FieldModelizable], parser: argparse.ArgumentParser, dest: str, partial: bool
):
    m = model(t)
    for fld in m.fields:
        if fld.name.startswith("_"):  # pragma: no cover
            continue
        fdest = _compose(dest, fld.name)
        overrides = {"required": False} if partial else {}
        add_argument_from_field(parser, fdest, overrides, fld)
    return parser


@ovld
def add_arguments(t: type[UnionAlias], parser: argparse.ArgumentParser, dest: str, partial: bool):
    options = [o for o in get_args(t) if o is not NoneType]
    recurse(options, parser, dest, partial)


@ovld
def add_arguments(options: list, parser: argparse.ArgumentParser, dest: str, partial: bool):
    if any(not issubclass(option, Tagged) for option in options):  # pragma: no cover
        if len(options) == 1:
            return recurse(options[0], parser, dest, partial)
        else:
            raise ValidationError("All Union members must be Tagged to make a cli")

    subparsers = parser.add_subparsers(dest=_compose(dest, "class"), required=True)
    for opt in options:
        subparser = subparsers.add_parser(opt.tag, help=f"{strip_all(opt.cls).__doc__ or opt.tag}")
        recurse(opt.cls, subparser, dest, partial)


@ovld
def add_arguments(t: type[Tagged], parser: argparse.ArgumentParser, dest: str, partial: bool):
    recurse([t], parser, dest, partial)


@dataclass
class CLIDefinition:
    root_type: type = None
    mapping: dict[str, str | dict[str, Any]] = field(default_factory=lambda: {"": {"auto": True}})
    argparser: argparse.ArgumentParser = None
    description: str = None

    def __post_init__(self):
        if self.argparser is None:
            if self.description is None:
                description = (
                    self.root_type.__doc__ or f"Arguments for {clsstring(self.root_type)}"
                )
            else:
                description = self.description
        self.argparser = argparse.ArgumentParser(description=description)
        for k, v in self.mapping.items():
            fld = field_at(self.root_type, k)
            if isinstance(v, str):
                v = {"__args__": [v]}
            elif v.pop("auto", False):
                add_arguments(fld.type, self.argparser, k, bool(v))
                if not v:
                    continue
            add_argument_from_field(self.argparser, k, v, fld)

    def __call__(self, argv):
        ns = self.argparser.parse_args(argv)
        values = {k: v for k, v in vars(ns).items() if v is not None}
        if (root := values.pop("", None)) is not None:
            vals = Sources(root, unflatten(values))
        else:
            vals = unflatten(values)
        return vals


def parse_cli(root_type, argv=None, mapping=None, description=None):
    mapping = {"": {"auto": True}} if mapping is None else mapping
    argv = sys.argv[1:] if argv is None else argv
    parser = CLIDefinition(root_type=root_type, mapping=mapping, description=description)
    return parser(argv)


class FromArguments(Medley):
    @ovld(priority=1)
    def deserialize(self, t: Any, obj: CommandLineArguments, ctx: Context):
        vals = obj.parse(t, obj.arguments)
        return recurse(t, vals, ctx)


# Add as a default feature in serieux.Serieux
__default_features__ = FromArguments
