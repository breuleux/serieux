import argparse
from dataclasses import MISSING, dataclass
from enum import Enum
from typing import get_args

from ovld import Medley, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import strip_all
from ..model import Field, Modelizable, model
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


@ovld
def make_argument(t: type[int] | type[float] | type[str], partial: dict, model_field: Field):
    return {**partial, "type": t}


@ovld
def make_argument(t: type[bool], partial: dict, model_field: Field):
    partial.pop("metavar", None)
    partial.pop("type", None)
    return {**partial, "action": argparse.BooleanOptionalAction}


@ovld(priority=1)
def make_argument(t: type[Enum], partial: dict, model_field: Field):
    return {**partial, "type": str, "choices": [e.value for e in t]}


@ovld
def make_argument(t: type[object], partial: dict, model_field: Field):
    return {**partial, "type": str}


@ovld
def make_argument(t: type[UnionAlias], partial: dict, model_field: Field):
    return "subparser"


@ovld
def add_arguments(t: type[Modelizable], parser: argparse.ArgumentParser, dest: str):
    m = model(t)
    for field in m.fields:
        if field.name.startswith("_"):  # pragma: no cover
            continue

        name = field.name.replace("_", "-")
        typ = strip_all(field.type)
        meta = dict(field.metadata.get("argparse", {}))
        positional = meta.pop("positional", False)
        fdest = _compose(dest, field.name)
        fhelp = field.description or field.name
        mvar = name.split(".")[-1].upper()

        if positional:
            args = {"__args__": [fdest], "help": fhelp, "metavar": mvar}
        else:
            args = {
                "__args__": [f"--{name}" if len(name) > 1 else f"-{name}"],
                "help": fhelp,
                "metavar": mvar,
                "required": field.required,
                "dest": fdest,
            }

        if field.default is not MISSING:
            args["default"] = field.default

        args = make_argument(typ, args, field)
        if args == "subparser":
            add_arguments(typ, parser, _compose(dest, field.name))
        else:
            pos = args.pop("__args__")
            if opt := meta.pop("option", None):
                if not isinstance(opt, list):
                    opt = [opt]
                pos[:] = opt
            if alias := meta.pop("alias", None):
                if not isinstance(alias, list):
                    alias = [alias]
                pos.extend(alias)
            args.update(meta)
            parser.add_argument(*pos, **args)
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


class FromArguments(Medley):
    @ovld(priority=1)
    def deserialize(self, t: type[object], obj: CommandLineArguments, ctx: Context):
        parser = argparse.ArgumentParser(description=t.__doc__ or f"Arguments for {clsstring(t)}")
        add_arguments(t, parser, "")
        ns = parser.parse_args(obj.arguments)
        values = {k: v for k, v in vars(ns).items() if v is not None}
        return recurse(t, unflatten(values), ctx)


# Add as a default feature in serieux.Serieux
__default_features__ = FromArguments
