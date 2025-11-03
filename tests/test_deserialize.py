import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pytest

from serieux import deserialize
from serieux.ctx import Trail, empty
from serieux.exc import ValidationError, display
from serieux.model import AllowExtras

from .common import has_312_features, one_test_per_assert
from .definitions import (
    Character,
    Color,
    Defaults,
    DIDHolder,
    DotDict,
    IdentifiedCar,
    Level,
    LTHolder,
    Point,
    Point3D,
    Pointato,
)

here = Path(__file__).parent


@one_test_per_assert
def test_deserialize_scalars():
    assert deserialize(int, 0) == 0
    assert deserialize(int, 12) == 12
    assert deserialize(float, -3.25) == -3.25
    assert deserialize(str, "flagada") == "flagada"
    assert deserialize(bool, True) is True
    assert deserialize(bool, False) is False
    assert deserialize(type(None), None) is None


@one_test_per_assert
def test_deserialize_scalars_conversion():
    assert deserialize(float, 10) == 10.0


@one_test_per_assert
def test_deserialize_object():
    assert deserialize(object, 10) == 10
    assert deserialize(Any, 10) == 10


def test_deserialize_dict():
    assert deserialize(dict[str, int], {"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_deserialize_point():
    assert deserialize(Point, {"x": 1, "y": 2}) == Point(1, 2)


def test_deserialize_list_of_points():
    pts = [
        {"x": 1, "y": 2},
        {"x": 3, "y": 4},
    ]
    assert deserialize(list[Point], pts) == [Point(1, 2), Point(3, 4)]


def test_deserialize_dict_of_points():
    pts = {
        "pt1": {"x": 1, "y": 2},
        "pt2": {"x": 3, "y": 4},
    }
    assert deserialize(dict[str, Point], pts) == {
        "pt1": Point(1, 2),
        "pt2": Point(3, 4),
    }


def test_deserialize_set():
    nums = [1, 4, 2, 3, 3, 4]
    assert deserialize(set[int], nums) == {1, 2, 3, 4}


def test_deserialize_frozenset():
    nums = [1, 4, 2, 3, 3, 4]
    assert deserialize(frozenset[int], nums) == frozenset({1, 2, 3, 4})


def test_deserialize_dict_subclass():
    data = {"apple": 3, "banana": 7}
    deser = deserialize(DotDict[str, int], data)
    assert deser.apple == 3
    assert deser.banana == 7


@one_test_per_assert
def test_deserialize_union():
    assert deserialize(str | int, 3) == 3
    assert deserialize(str | int, "wow") == "wow"
    assert deserialize(Point | int, 3) == 3


@dataclass
class Poink:
    x: int
    y: int


def test_cannot_deserialize_undistinguishable():
    with pytest.raises(Exception, match="Cannot differentiate"):
        deserialize(Point | Poink, {"x": 1, "y": 2})


@has_312_features
def test_deserialize_tree():
    from .definitions_py312 import Tree

    tree = {
        "left": {
            "left": 1,
            "right": 2,
        },
        "right": {
            "left": {
                "left": {
                    "left": 3,
                    "right": 4,
                },
                "right": 5,
            },
            "right": 6,
        },
    }

    assert deserialize(Tree[int], tree) == Tree(Tree(1, 2), Tree(Tree(Tree(3, 4), 5), 6))


def test_deserialize_overlapping_union():
    P = Point | Point3D
    assert type(deserialize(P, {"x": 1, "y": 2})) is Point
    assert type(deserialize(P, {"x": 1, "y": 2, "z": 3})) is Point3D

    # Make sure it also works the other way around
    P = Point3D | Point
    assert type(deserialize(P, {"x": 1, "y": 2})) is Point
    assert type(deserialize(P, {"x": 1, "y": 2, "z": 3})) is Point3D


def test_deserialize_defaults():
    data1 = {"name": "bob"}
    data2 = {"cool": True, "name": "alice"}

    x1 = deserialize(Defaults, data1)
    assert not x1.cool

    x2 = deserialize(Defaults, data2)
    assert x2.cool

    assert not x1.aliases
    assert not x2.aliases
    assert x1.aliases is not x2.aliases


def test_deserialize_enum():
    assert deserialize(Color, "red") == Color.RED
    assert deserialize(list[Color], ["green", "blue", "green"]) == [
        Color.GREEN,
        Color.BLUE,
        Color.GREEN,
    ]


def test_deserialize_enum_int():
    assert deserialize(Level, 1) == Level.MED
    assert deserialize(list[Level], [2, 0, 2]) == [Level.HI, Level.LO, Level.HI]


def test_deserialize_literal_enum():
    assert deserialize(Literal["red", "green", "blue"], "red") == "red"
    with pytest.raises(
        ValidationError,
        match=r"'yellow' is not a valid option for typing.Literal\['red', 'green', 'blue'\]",
    ):
        deserialize(Literal["red", "green", "blue"], "yellow")


def test_deserialize_literal_int_enum():
    assert deserialize(Literal[1, 2, 7], 2) == 2
    with pytest.raises(
        ValidationError,
        match=r"'3' is not a valid option for typing.Literal\[1, 2, 7\]",
    ):
        deserialize(Literal[1, 2, 7], 3)


def test_deserialize_literal_mixed_enum():
    lit = Literal[1, True, "quack"]
    assert deserialize(lit, 1) == 1
    assert deserialize(lit, True) is True
    assert deserialize(lit, "quack") == "quack"
    with pytest.raises(ValidationError):
        deserialize(lit, 3)
    with pytest.raises(ValidationError):
        deserialize(lit, "boop")
    with pytest.raises(ValidationError):
        deserialize(lit, False)


###############
# Error tests #
###############


def test_deserialize_scalar_error():
    with pytest.raises(ValidationError, match=r"Cannot deserialize string 'foo'"):
        deserialize(int, "foo")


def test_deserialize_scalar_error_2():
    with pytest.raises(ValidationError, match=r"Cannot deserialize object `13`"):
        deserialize(str, 13)


@pytest.mark.parametrize("ctx", (Trail(), empty))
def test_deserialize_missing_field(ctx):
    pts = [
        {"x": 1, "y": 2},
        {"x": 3},
    ]
    with pytest.raises(ValidationError, match=r"At path .1: Missing required field 'y'"):
        deserialize(list[Point], pts, ctx)


def test_deserialize_extra_fields_not_allowed():
    data = {"x": 1, "y": 2, "poop": 123}
    with pytest.raises(ValidationError, match=r"Extra unrecognized fields.*Point.*poop"):
        deserialize(Point, data)


def test_deserialize_extra_fields_allowed():
    data = {"x": 1, "y": 2, "poop": 123}
    assert deserialize(AllowExtras[Point], data) == Point(1, 2)


def test_deserialize_extra_fields_allowed_in_config():
    data = {
        "name": "Billy",
        "age": 28,
        "occupation": "Wizard",
        "backstory": "Mysterious",
        "splat": 99,
        "splatity_splat": True,
    }
    assert deserialize(Character, data) == Character(
        name="Billy", age=28, occupation="Wizard", backstory="Mysterious"
    )


def test_error_display(capsys, file_regression):
    pts = [
        {"x": 1, "y": 2},
        {"x": 3},
    ]
    with pytest.raises(ValidationError, match=r"At path .1: Missing required field 'y'") as exc:
        deserialize(list[Point], pts)

    display(exc.value, sys.stderr)
    cap = capsys.readouterr()
    file_regression.check("\n".join([cap.out, "=" * 80, cap.err]))


def test_deserialize_recursive_type():
    data = {
        "did": {
            "a": 1,
            "b": {
                "c": 2,
                "d": 3,
            },
        }
    }
    deser = deserialize(DIDHolder, data)
    assert deser.did == data["did"]


def test_deserialize_recursive_type_2():
    def p(x):
        return Point(x, x)

    data = {"lt": [{"x": 1, "y": 1}, [{"x": 2, "y": 2}, [{"x": 3, "y": 3}], {"x": 4, "y": 4}]]}
    deser = deserialize(LTHolder, data)
    assert deser.lt == [p(1), [p(2), [p(3)], p(4)]]


@pytest.mark.skipif(sys.version_info < (3, 12), reason="Requires Python 3.12+")
def test_deserialize_recursive_type_py312():
    from .definitions_py312 import LTHolder, Point

    def p(x):
        return Point(x, x)

    data = {"lt": [{"x": 1, "y": 1}, [{"x": 2, "y": 2}, [{"x": 3, "y": 3}], {"x": 4, "y": 4}]]}
    deser = deserialize(LTHolder, data)
    assert deser.lt == [p(1), [p(2), [p(3)], p(4)]]


class Blooper:
    def __init__(self, x: int, y: int, txt: str):
        self.message = txt * (x + y)


def test_deserialize_from_init():
    data = {"x": 2, "y": 3, "txt": "ha"}
    blooper = deserialize(Blooper, data)
    assert isinstance(blooper, Blooper)
    assert blooper.message == "hahahahaha"


def test_deserialize_pointato():
    with pytest.raises(ValidationError, match="Did you mean for it to be a dataclass"):
        deserialize(Pointato, {"x": 1, "y": 2})


def test_deserialize_kwonly_fields():
    data = {"id": 42, "horsepower": 300}
    car = deserialize(IdentifiedCar, data)
    assert car == IdentifiedCar(42, horsepower=300)
