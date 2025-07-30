from dataclasses import dataclass

import pytest

from serieux import deserialize, serialize
from serieux.auto import Auto, Call
from serieux.exc import SchemaError, ValidationError
from serieux.features.tagset import TaggedUnion, tag_field
from serieux.model import constructed_type

from .definitions import Point


class Funky:
    def __init__(self, x: int, y: bool):
        self.marks = funky(x, y)


def funky(x: int, y: bool) -> str:
    return ("!" if y else ".") * x


@dataclass
class HoldsFunk:
    funk: Funky
    more: bool


def test_auto():
    funk = deserialize(Auto[Funky], {"x": 3, "y": True})
    assert funk.marks == "!!!"


def test_auto_from_init():
    funk = deserialize(Auto[Funky], {"x": 3, "y": True})
    assert funk.marks == "!!!"


def test_auto_callable():
    funk = deserialize(Auto[funky], {"x": 3, "y": True})
    assert funk() == "!!!"


def test_call_callable():
    funk = deserialize(Call[funky], {"x": 3, "y": True})
    assert funk == "!!!"


def test_call_on_type():
    with pytest.raises(TypeError, match=r"Call\[...\] should only wrap callables"):
        deserialize(Call[Funky], {"x": 3, "y": True})


def test_auto_not_serializable():
    with pytest.raises(SchemaError, match="does not specify how to serialize"):
        serialize(Auto[Funky], Funky(x=3, y=True))


def test_auto_inherit():
    hfunk = deserialize(Auto[HoldsFunk], {"more": True, "funk": {"x": 3, "y": True}})
    assert hfunk.funk.marks == "!!!"


def test_auto_no_interference():
    pt = serialize(Auto[Point], Point(1, 2))
    assert pt == {"x": 1, "y": 2}


def add_them(x: int, y: int):
    return x + y


def mul_them(x: int, y: int) -> int:
    return x * y


def test_tagged_union():
    tu = TaggedUnion[Call[add_them], Call[mul_them]]

    result = deserialize(tu, {tag_field: "add_them", "x": 3, "y": 4})
    assert result == 7

    result = deserialize(tu, {tag_field: "mul_them", "x": 3, "y": 4})
    assert result == 12

    with pytest.raises(ValidationError, match="does not match expected tag"):
        deserialize(tu, {tag_field: "div_them", "x": 3, "y": 4})


def test_constructed_type():
    assert constructed_type(Call[mul_them]) is int
    with pytest.raises(TypeError, match="does not have a return type annotation"):
        constructed_type(Call[add_them])
