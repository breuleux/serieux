import traceback
from contextlib import contextmanager
from pathlib import Path

import pytest

from serieux import DataConverter, ValidationExceptionGroup, deserialize
from serieux.formats import YamlMixin
from serieux.model import Multiple
from serieux.proxy import Accessor

from .common import Citizen, Country, Point, one_test_per_assert

here = Path(__file__).parent


# Plain deserialization


@one_test_per_assert
def test_deserialize_scalars():
    assert deserialize(int, 0) == 0
    assert deserialize(int, 12) == 12
    assert deserialize(float, -3.25) == -3.25
    assert deserialize(str, "flagada") == "flagada"
    assert deserialize(bool, True) is True
    assert deserialize(bool, False) is False
    assert deserialize(type(None), None) is None


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


# Errors


@contextmanager
def validation_errors(msgs):
    try:
        yield
    except ValidationExceptionGroup as veg:
        for pth, msg in msgs.items():
            if not any(
                (str(exc.ctx[Accessor]) == pth and msg in str(exc))
                for exc in veg.exceptions
            ):
                traceback.print_exception(veg)
                raise Exception(f"No exception was raised at {pth} for '{msg}'")


def test_deserialize_missing_field():
    pts = [
        {"x": 1, "y": 2},
        {"x": 3},
    ]
    with validation_errors({"[1]": "missing 1 required positional argument"}):
        deserialize(list[Point], pts)


def test_deserialize_extra_field():
    pts = [
        {"x": 1, "y": 2},
        {"x": 1, "y": 2, "z": 3},
    ]
    with validation_errors({"[1].z": "Unknown field"}):
        deserialize(list[Point], pts)


def test_deserialize_multiple_errors():
    pt = {"x": [1], "y": [2]}
    with validation_errors(
        {
            ".x": "incompatible type `list`",
            ".y": "incompatible type `list`",
        }
    ):
        deserialize(Point, pt)


# Deserialization from a file


@pytest.fixture(scope="module")
def yaml_deserialize():
    YDC = DataConverter.create_subclass(YamlMixin)
    yield YDC().deserialize


def test_deserialize_from_file(yaml_deserialize):
    assert yaml_deserialize(Country, here / "data" / "canada.yaml") == Country(
        languages=["English", "French"],
        capital="Ottawa",
        population=39_000_000,
        citizens=[
            Citizen(
                name="Olivier",
                birthyear=1985,
                hometown="Montreal",
            ),
            Citizen(
                name="Abraham",
                birthyear=2018,
                hometown="Shawinigan",
            ),
        ],
    )


def test_deserialize_incomplete_file(yaml_deserialize):
    with validation_errors({"": "missing 1 required positional"}):
        yaml_deserialize(Country, here / "data" / "france.yaml")


def test_deserialize_point_two_sources():
    assert deserialize(Point, Multiple([{"x": 1}, {"y": 2}])) == Point(1, 2)
