from dataclasses import dataclass

import pytest

from serieux import deserialize, serialize
from serieux.auto import Auto, Call
from serieux.exc import SchemaError

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
