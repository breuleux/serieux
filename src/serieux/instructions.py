from dataclasses import dataclass
from types import UnionType
from typing import Annotated, Literal, TypeVar, Union, get_args, get_origin

T = TypeVar("T")


class InstructionMC(type):
    def __rmatmul__(cls, t):
        return Annotated[t, cls]

    def decompose(cls, t, all=False):
        method = cls.extract_all if all else cls.extract
        return strip(t, cls), method(t)

    def extract(cls, t):
        for x in cls.extract_all(t):
            return x
        return None

    def extract_all(cls, t):
        if get_origin(t) is not Annotated:
            return
        for x in t.__metadata__:
            if isinstance(x, cls):
                yield x

    @property
    def annotation_priority(cls):
        return 1


class BaseInstruction(metaclass=InstructionMC):
    def strip(self, t):
        return strip(t, self)

    def __rmatmul__(self, t):
        return Annotated[t, self]


@dataclass(frozen=True)
class Instruction(BaseInstruction):
    name: str
    annotation_priority: int = 1
    inherit: bool = True

    def __getitem__(self, t):
        return Annotated[t, self]

    def __str__(self):
        return self.name

    __repr__ = __str__


def has_instruction(cls, instr):
    return get_origin(cls) is Annotated and any(
        (isinstance(instr, type) and isinstance(a, instr)) or a == instr for a in cls.__metadata__
    )


def annotate(cls, annotations):
    if get_origin(annotations) is Annotated:
        annotations = annotations.__metadata__
    if not annotations:
        return cls
    else:
        return Annotated[(cls, *annotations)]


def strip(cls, to_remove=None):
    def should_remove(a):
        if to_remove is None:
            return True
        if isinstance(to_remove, type):
            return isinstance(a, to_remove)
        else:
            return a == to_remove

    if get_origin(cls) is not Annotated:
        return cls
    anns = [a for a in cls.__metadata__ if not should_remove(a)]
    return annotate(get_args(cls)[0], anns)


def inherit(cls, target):
    if get_origin(cls) is not Annotated:
        return target
    _, *instrs = get_args(cls)
    new_instrs = [a for a in instrs if getattr(a, "inherit", False)]
    if not new_instrs:
        return target
    return Annotated[(target, *new_instrs)]


def pushdown(cls):
    if get_origin(cls) is not Annotated:
        return cls
    typ, *instrs = get_args(cls)
    new_instrs = [a for a in instrs if getattr(a, "inherit", False)]
    if not new_instrs:
        return typ
    if (orig := get_origin(typ)) and orig is not Literal:
        args = get_args(typ)
        if orig is UnionType:
            orig = Union
        return orig[tuple([Annotated[(a, *new_instrs)] for a in args])]
    else:
        return typ
