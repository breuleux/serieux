from ovld import Code, Lambda

from serieux.module import Module, create
from serieux.state import State
from tests.common import Point

twicer = Module()
caser = Module()
pointer = Module()


@twicer.serializer
def _(self, t: type[int], obj: int, state: State, /):
    return obj * 2


@twicer.deserializer
def _(self, t: type[int], obj: int, state: State, /):
    return obj // 2


@caser.serializer
def _(self, t: type[str], obj: str, state: State, /):
    return obj.upper()


@caser.deserializer
def _(self, t: type[str], obj: str, state: State, /):
    return obj.lower()


@pointer.serializer(codegen=True)
def _(self, t: type[Point], obj: Point, state: State, /):
    return Lambda(Code("{'x': $obj.x * 10, 'y': $obj.y * 100}"))


def test_twicer():
    ifc = create(twicer)
    assert ifc.serialize(4) == 8
    assert ifc.deserialize(4) == 2
    assert ifc.deserialize(list[int], [10, 4, 6]) == [5, 2, 3]


def test_multiple_modules():
    ifc = create(twicer, caser)
    assert ifc.serialize(4) == 8
    assert ifc.deserialize(4) == 2
    assert ifc.serialize("wow") == "WOW"
    assert ifc.deserialize("WOW") == "wow"


def test_custom_codegen():
    ifc = create(pointer)
    assert ifc.serialize(Point(4, 5)) == {"x": 40, "y": 500}
