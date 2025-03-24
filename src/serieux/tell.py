from dataclasses import dataclass, fields
from typing import get_origin

from ovld import Code, Dataclass, ovld

from .model import Modell as Model


class Tell:
    def __lt__(self, other):
        return self.cost() < other.cost()

    def cost(self):
        return 1


@dataclass(frozen=True)
class TypeTell(Tell):
    t: type

    def gen(self, arg):
        return Code("isinstance($arg, $t)", arg=arg, t=self.t)


@dataclass(frozen=True)
class KeyTell(Tell):
    key: str

    def gen(self, arg):
        return Code("(isinstance($arg, dict) and $k in $arg)", arg=arg, k=self.key)

    def cost(self):
        return 2


@ovld
def tells(typ: type[int] | type[str] | type[bool] | type[float] | type[list] | type[dict]):
    return {TypeTell(typ)}


@ovld
def tells(dc: type[Dataclass]):
    dc = get_origin(dc) or dc
    return {TypeTell(dict)} | {KeyTell(f.name) for f in fields(dc)}


@ovld
def tells(m: type[Model]):
    return {TypeTell(dict)} | {KeyTell(f.serialized_name) for f in m.fields}
