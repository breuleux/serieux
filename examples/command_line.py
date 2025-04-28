import argparse
import sys
from dataclasses import dataclass
from functools import cache

from ovld import Medley, recurse
from ovld.dependent import Regexp
from rich.pretty import pprint

from serieux import Serieux, Sources, deserialize
from serieux.ctx import Context
from serieux.instructions import strip_all
from serieux.model import FieldModelizable, model

##################
# Implementation #
##################


@dataclass
class CommandLineArguments:
    arguments: list[str]


@cache
def parser_for(t: type):
    m = model(t)
    parser = argparse.ArgumentParser(description=f"Arguments for {m.original_type.__name__}")
    for field in m.fields:
        if not field.name.startswith("_"):
            typ = strip_all(field.type)
            if typ not in (int, float, str, bool):
                typ = str
            parser.add_argument(
                f"--{field.name}",
                type=typ,
                help=field.description or field.name,
                required=field.required,
            )
    return parser


@Serieux.extend
class FromArguments(Medley):
    def deserialize(self, t: type[FieldModelizable], obj: CommandLineArguments, ctx: Context):
        parser = parser_for(t)
        ns = parser.parse_args(obj.arguments)
        values = {k: v for k, v in vars(ns).items() if v is not None}
        return recurse(t, values, ctx)


#################
# Demonstration #
#################


@dataclass
class RGB:
    red: int
    green: int
    blue: int


@Serieux.extend
class RGBSerializer(Medley):
    def deserialize(self, t: type[RGB], obj: Regexp[r"^#[0-9a-fA-F]{6}$"], ctx: Context):
        hex_str = obj.lstrip("#")
        red = int(hex_str[0:2], 16)
        green = int(hex_str[2:4], 16)
        blue = int(hex_str[4:6], 16)
        return RGB(red=red, green=green, blue=blue)


@dataclass
class Person:
    # Name of the person
    name: str
    # Age of the person
    age: int
    # The person's shirt color
    shirt: RGB


def main(argv=["--name", "Travis", "--shirt", "#ff0010"]):
    defaults = {"name": "Guy", "age": 0, "shirt": "#ffffff"}
    overrides = {"shirt": {"blue": 128}}
    person = deserialize(Person, Sources(defaults, CommandLineArguments(argv), overrides))
    pprint(person, expand_all=True)


if __name__ == "__main__":
    main(sys.argv[1:])
