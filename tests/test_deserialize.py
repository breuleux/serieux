from pathlib import Path

import pytest

from serieux.deserialization import deserialize
from serieux.exc import ValidationError

from .common import Point, one_test_per_assert

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


def test_deserialize_scalar_error():
    with pytest.raises(ValidationError, match=r"No way to deserialize"):
        deserialize(int, "foo")


def test_deserialize_missing_field():
    pts = [
        {"x": 1, "y": 2},
        {"x": 3},
    ]
    with pytest.raises(ValidationError, match=r"At path \[1\]: KeyError: 'y'"):
        deserialize(list[Point], pts)
