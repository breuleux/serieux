from dataclasses import dataclass

from ovld import Code, ovld, recurse

from .instructions import InstructionType
from .model import Modelizable, model


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


@dataclass(frozen=True)
class KeyValueTell(Tell):
    key: str
    value: object

    def gen(self, arg):
        return Code(
            "(isinstance($arg, dict) and $k in $arg and $arg[$k] == $v)",
            arg=arg,
            k=self.key,
            v=self.value,
        )

    def cost(self):  # pragma: no cover
        return 3


@ovld
def tells(typ: type[int] | type[str] | type[bool] | type[float] | type[list] | type[dict]):
    return {TypeTell(typ)}


@ovld
def tells(typ: type[Modelizable]):
    m = model(typ)
    return {TypeTell(dict)} | {KeyTell(f.serialized_name) for f in m.fields}


@ovld(priority=-1)
def tells(m: type[InstructionType]):
    return recurse(m.pushdown())
