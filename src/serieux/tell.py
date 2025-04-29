from dataclasses import dataclass
from pathlib import Path
from types import NoneType

from ovld import Code, ovld, recurse

from .instructions import InstructionType
from .model import FieldModelizable, StringModelizable, model
from .utils import TypeAliasType, basic_type


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
def tells(
    typ: type[int]
    | type[str]
    | type[bool]
    | type[float]
    | type[NoneType]
    | type[list]
    | type[dict],
):
    return {TypeTell(basic_type(typ))}


@ovld
def tells(typ: type[Path]):
    return {TypeTell(str)}


@ovld
def tells(typ: type[FieldModelizable]):
    m = model(typ)
    return {TypeTell(dict)} | {KeyTell(f.serialized_name) for f in m.fields}


@ovld
def tells(typ: type[StringModelizable]):
    return {TypeTell(str)}


@ovld
def tells(typ: TypeAliasType):
    return recurse(typ.__value__)


@ovld(priority=-1)
def tells(typ: type[InstructionType]):
    return recurse(typ.pushdown())
