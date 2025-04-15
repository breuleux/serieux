from dataclasses import dataclass

import pytest
from ovld import Medley
from ovld.dependent import Regexp

from serieux import Serieux
from serieux.ctx import AccessPath, Context
from serieux.exc import SerieuxError, ValidationError
from serieux.features.partial import Partial, PartialBuilding, Sources

from ..common import validation_errors
from ..definitions import Defaults, Player, Point

deserialize = (Serieux + PartialBuilding)().deserialize


def test_partial():
    one = deserialize(Partial[Point], {"x": 10})
    assert one.x == 10
    two = deserialize(Partial[Point], {"y": 30})
    assert two.y == 30


def test_partial_error():
    value = deserialize(Partial[Point], {"x": "oh", "y": "no"})
    assert isinstance(value.x, ValidationError)
    assert isinstance(value.y, ValidationError)


def test_two_sources():
    assert deserialize(Point, Sources({"x": 1}, {"y": 2})) == Point(1, 2)


def test_three_sources():
    assert deserialize(Point, Sources({"x": 1}, {"y": 2}, {"x": 3})) == Point(3, 2)


def test_complicated_partial():
    d = deserialize(
        dict[str, Point | str],
        Sources(
            {"a": {"x": 1, "y": 2}},
            {"a": {"x": 3}},
            {"b": "wow"},
        ),
    )
    assert d == {"a": Point(3, 2), "b": "wow"}


def test_merge_lists():
    li = deserialize(
        list[int],
        Sources(
            [1, 2],
            [3, 4, 5],
        ),
    )
    assert li == [1, 2, 3, 4, 5]


def test_partial_incompatibility():
    with pytest.raises(ValidationError, match="incompatible constructors"):
        deserialize(
            Point | Player,
            Sources({"x": 1, "y": 2}, {"first": "Joan", "last": "Ark", "batting": 0.7}),
        )


def test_partial_incompatibility_2():
    with pytest.raises(ValidationError, match="incompatible constructors"):
        deserialize(Point | str, Sources({"x": 1, "y": 2}, "waa"))


def test_partial_incompatibility_3():
    with pytest.raises(ValidationError, match="incompatible constructors"):
        deserialize(Point | str, Sources("waa", {"x": 1, "y": 2}))


@dataclass
class Climate:
    hot: bool
    sunny: bool


@dataclass
class City:
    name: str
    population: int
    climate: Climate


@dataclass
class Country:
    name: str
    capital: City


def test_nested():
    d = deserialize(
        Country,
        Sources(
            {"name": "Canada"},
            {"capital": {"name": "Ottawa"}},
            {"capital": {"population": 800000}},
            {"capital": {"climate": {"hot": False}}},
            {"capital": {"climate": {"sunny": False}}},
        ),
    )
    assert d == Country(
        name="Canada",
        capital=City(
            name="Ottawa",
            population=800_000,
            climate=Climate(
                hot=False,
                sunny=False,
            ),
        ),
    )


@dataclass
class Positive:
    m: int
    n: int

    def __post_init__(self):
        if self.m <= 0:
            raise ValueError("NO")
        if self.n <= 0:
            raise ValueError("Get that worthless number outta here")


def test_error_at_construction():
    with pytest.raises(ValidationError, match="At path .1"):
        deserialize(list[Positive], [{"m": 3, "n": 7}, Sources({"m": 1}, {"n": -3})], AccessPath())


def test_multiple_errors():
    msg = "Cannot deserialize object of type 'str' into expected type 'int'."
    with validation_errors({".0.y": msg, ".1.x": msg, ".1.y": msg}):
        deserialize(
            list[Point], Sources([{"x": 23, "y": "crap"}, {"x": "oh", "y": "no"}]), AccessPath()
        )


def test_multiple_errors_display(check_error_display):
    with check_error_display():
        deserialize(
            list[Point], Sources([{"x": 23, "y": "crap"}, {"x": "oh", "y": "no"}]), AccessPath()
        )


def test_partial_defaults():
    result = deserialize(Defaults, Sources({"name": "Nicolas"}, {"cool": True}))
    assert result == Defaults(name="Nicolas", aliases=[], cool=True)


@dataclass
class RGB:
    red: int
    green: int
    blue: int


@Serieux.extend
class RGBSerializer(Medley):
    def deserialize(self, t: type[RGB], obj: Regexp[r"^#[0-9a-fA-F]{6}$"], ctx: Context):
        hex_str = obj.lstrip("#")
        red = int(hex_str[0:2], 16)
        green = int(hex_str[2:4], 16)
        blue = int(hex_str[4:6], 16)
        return RGB(red=red, green=green, blue=blue)


def test_merge_partial_with_object():
    assert deserialize(RGB, Sources({"red": 0}, "#ffffff")) == RGB(255, 255, 255)
    assert deserialize(RGB, Sources("#ffffff", {"red": 0})) == RGB(0, 255, 255)

    with pytest.raises(SerieuxError, match="Cannot deserialize"):
        deserialize(RGB, Sources("#fffffX", {"red": 0}))

    with pytest.raises(SerieuxError, match="Cannot deserialize"):
        deserialize(RGB, Sources({"red": 0}, "#fffffX"))

    with pytest.raises(SerieuxError, match="Some errors occurred"):
        deserialize(RGB, Sources("#fffffX", "#fffffX"))
