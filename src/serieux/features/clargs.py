import argparse
from dataclasses import MISSING, dataclass, field
from enum import Enum
from typing import Any, get_args

from ovld import Medley, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import strip_all
from ..model import Field, Modelizable, field_at, model
from ..utils import UnionAlias, clsstring
from .dotted import unflatten
from .tagged import Tagged

##################
# Implementation #
##################


def _compose(dest, new_part):
    return f"{dest}.{new_part}" if dest else new_part


@dataclass
class CommandLineArguments:
    arguments: list[str]
    mapping: dict[str, str | dict[str, Any]] = field(default_factory=dict)
    autofill: bool = True

    def make_parser(self, base):
        return make_parser(base=base, mapping=self.mapping, autofill=self.autofill)


class ConcatenateAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, " ".join(values))


@ovld
def make_argument(t: type[str], partial: dict, model_field: Field):
    rval = {**partial, "type": t}
    if "nargs" in partial and "action" not in partial:
        rval["action"] = ConcatenateAction
    return rval


@ovld
def make_argument(t: type[int] | type[float], partial: dict, model_field: Field):
    return {**partial, "type": t}


@ovld
def make_argument(t: type[bool], partial: dict, model_field: Field):
    partial.pop("metavar", None)
    partial.pop("type", None)
    return {**partial, "action": argparse.BooleanOptionalAction}


@ovld
def make_argument(t: type[list], partial: dict, model_field: Field):
    (lt,) = get_args(t) or (object,)
    return {"nargs": "*", "type": lt, **partial}


@ovld(priority=1)
def make_argument(t: type[Enum], partial: dict, model_field: Field):
    return {**partial, "type": str, "choices": [e.value for e in t]}


@ovld
def make_argument(t: type[object], partial: dict, model_field: Field):
    return {**partial, "type": str}


@ovld
def make_argument(t: type[UnionAlias], partial: dict, model_field: Field):
    return "subparser"


def add_argument_from_field(parser, fdest, overrides, field: Field):
    name = field.name.replace("_", "-")
    typ = strip_all(field.type)
    meta = dict(field.metadata.get("argparse", {}))
    positional = meta.pop("positional", False)
    fhelp = field.description or field.name
    mvar = name.split(".")[-1].upper()

    if positional:
        args = {"__args__": [fdest], "help": fhelp, "metavar": mvar, **overrides}
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

    if field.default is not MISSING:
        args["default"] = field.default

    args = make_argument(typ, args, field)
    if args == "subparser":
        add_arguments(typ, parser, fdest)
    else:
        pos = args.pop("__args__")
        if opt := args.pop("option", None):
            if not isinstance(opt, list):
                opt = [opt]
            pos[:] = opt
        if alias := args.pop("alias", None):
            if not isinstance(alias, list):
                alias = [alias]
            pos.extend(alias)
        parser.add_argument(*pos, **args)


@ovld
def add_arguments(t: type[Modelizable], parser: argparse.ArgumentParser, dest: str):
    m = model(t)
    for fld in m.fields:
        if fld.name.startswith("_"):  # pragma: no cover
            continue
        fdest = _compose(dest, fld.name)
        add_argument_from_field(parser, fdest, {}, fld)
    return parser


@ovld
def add_arguments(t: type[UnionAlias], parser: argparse.ArgumentParser, dest: str):
    options = get_args(t)
    if any(not issubclass(option, Tagged) for option in options):  # pragma: no cover
        raise ValidationError("All Union members must be Tagged to make a cli")

    subparsers = parser.add_subparsers(dest=_compose(dest, "class"))
    for opt in options:
        subparsers.required = True
        subparser = subparsers.add_parser(opt.tag, help=f"{opt.cls.__doc__ or opt.tag}")
        add_arguments(opt.cls, subparser, dest)


def make_parser(*, base=None, mapping=None, parser=None, autofill=True):
    if parser is None:
        description = base.__doc__ or f"Arguments for {clsstring(base)}"
        parser = argparse.ArgumentParser(description=description)
    if autofill:
        add_arguments(base, parser, "")
    for k, v in mapping.items():
        if isinstance(v, str):
            v = {"__args__": [v]}
        fld = field_at(base, k)
        add_argument_from_field(parser, k, v, fld)
    return parser


class FromArguments(Medley):
    @ovld(priority=1)
    def deserialize(self, t: Any, obj: CommandLineArguments, ctx: Context):
        parser = obj.make_parser(t)
        ns = parser.parse_args(obj.arguments)
        values = {k: v for k, v in vars(ns).items() if v is not None}
        return recurse(t, unflatten(values), ctx)


# Add as a default feature in serieux.Serieux
__default_features__ = FromArguments
