from dataclasses import dataclass

import pytest

from serieux.ctx import AccessPath
from serieux.exc import ValidationError
from serieux.impl import BaseImplementation
from serieux.partial import Partial, PartialFeature, Sources
from tests.common import Point, validation_errors

deserialize = (BaseImplementation + PartialFeature)().deserialize


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
