from dataclasses import dataclass
from functools import cache
from types import UnionType
from typing import TypeVar, Union, get_args, get_origin

from ovld import subclasscheck
from ovld.mro import Order

T = TypeVar("T")


@dataclass(frozen=True)
class Instruction:
    name: str
    priority: int
    inherit: bool = True


def make_instruction(name, priority=1, inherit=True) -> type:
    instr = Instruction(name=name, priority=priority, inherit=inherit)
    return _create(frozenset({instr}), object)


class NewInstruction:
    def __class_getitem__(cls, params) -> type:
        _, *params = params
        return make_instruction(*params)


@cache
def _create(instrs, cls):
    if isinstance(cls, type) and issubclass(cls, InstructionType):
        return _create(instrs | cls._instructions, cls._cls)
    if not instrs:
        return cls
    else:
        name = "&".join(t.name for t in instrs)
        clsname = getattr(cls, "__name__", str(cls))
        return type(
            f"{name}[{clsname}]", (InstructionType,), {"_instructions": instrs, "_cls": cls}
        )


class InstructionType(type):
    _cls = object
    _instructions = frozenset()

    @classmethod
    def __is_supertype__(self, other):
        return (
            isinstance(other, type)
            and issubclass(other, InstructionType)
            and other._instructions.issuperset(self._instructions)
            and (self._cls is object or subclasscheck(other._cls, self._cls))
        )

    @classmethod
    def __type_order__(self, other):
        if not (isinstance(other, type) and issubclass(other, InstructionType)):
            return NotImplemented
        prio = tuple(sorted(tag.priority for tag in self._instructions))
        prio_o = tuple(sorted(tag.priority for tag in other._instructions))
        return Order.LESS if prio > prio_o else Order.MORE if prio < prio_o else Order.NONE

    def __class_getitem__(self, t):
        return _create(self._instructions, t)

    @classmethod
    def strip(cls, t):
        if isinstance(t, type) and issubclass(t, InstructionType):
            return _create(t._instructions - cls._instructions, t._cls)
        return t

    @classmethod
    def pushdown(cls):
        return pushdown(cls)

    @classmethod
    def inherit(cls, t):
        instrs = frozenset(i for i in cls._instructions if i.inherit)
        return _create(instrs, t)


def pushdown(cls):
    if not isinstance(cls, type) or not issubclass(cls, InstructionType):
        return cls
    typ = cls.strip(cls)
    cls = _create(
        cls._instructions - {tag for tag in cls._instructions if not tag.inherit}, cls._cls
    )
    if not isinstance(cls, type) or not issubclass(cls, InstructionType):
        return cls
    if orig := get_origin(typ):
        args = get_args(typ)
        if orig is UnionType:
            orig = Union
        return orig[tuple([cls[a] for a in args])]
    else:
        return typ


def strip_all(cls):
    if isinstance(cls, type) and issubclass(cls, InstructionType):
        return cls.strip(cls)
    return cls
