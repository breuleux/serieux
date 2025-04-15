from dataclasses import dataclass

import pytest

from serieux import deserialize, serialize
from serieux.auto import Auto
from serieux.exc import ValidationError

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


def test_auto_from_init():
    funk = deserialize(Auto[Funky], {"x": 3, "y": True})
    assert funk.marks == "!!!"


def test_auto_callable():
    funk = deserialize(Auto[funky], {"x": 3, "y": True})
    assert funk == "!!!"


def test_auto_not_serializable():
    with pytest.raises(ValidationError, match="does not specify how to serialize"):
        serialize(Auto[Funky], Funky(x=3, y=True))


def test_auto_inherit():
    hfunk = deserialize(Auto[HoldsFunk], {"more": True, "funk": {"x": 3, "y": True}})
    assert hfunk.funk.marks == "!!!"


def test_auto_no_interference():
    pt = serialize(Auto[Point], Point(1, 2))
    assert pt == {"x": 1, "y": 2}
