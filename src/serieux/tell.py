from dataclasses import dataclass
from pathlib import Path
from types import NoneType
from typing import Annotated, Any

from ovld import Code, ovld, recurse

from .instructions import pushdown
from .model import FieldModelizable, ListModelizable, StringModelizable, model


class Tell:
    def __lt__(self, other):
        return self.cost() < other.cost()

    def cost(self):  # pragma: no cover
        return 1


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
def tells(expected: type[int], given: type[int]):
    return set()


@ovld
def tells(expected: type[str] | type[Path] | type[StringModelizable], given: type[str]):
    return set()


@ovld
def tells(expected: type[bool], given: type[bool]):
    return set()


@ovld
def tells(expected: type[float], given: type[float]):
    return set()


@ovld
def tells(expected: type[NoneType], given: type[NoneType]):
    return set()


@ovld
def tells(expected: type[dict], given: type[dict]):
    return set()


@ovld
def tells(expected: type[FieldModelizable], given: type[dict]):
    m = model(expected)
    return {KeyTell(f.serialized_name) for f in m.fields}


@ovld
def tells(expected: type[ListModelizable], given: type[list]):
    return set()


@ovld
def tells(expected: type[Annotated], given: Any):
    return recurse(pushdown(expected), given)


@ovld(priority=-1)
def tells(expected: Any, given: Any):
    return None
