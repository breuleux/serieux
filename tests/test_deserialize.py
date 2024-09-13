import traceback
from contextlib import contextmanager
from pathlib import Path

from serieux import ValidationExceptionGroup, deserialize
from serieux.model import Multiple
from serieux.proxy import Accessor

from .common import Point

here = Path(__file__).parent


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


def test_deserialize_point():
    assert deserialize(Point, {"x": 1, "y": 2}) == Point(1, 2)


def test_deserialize_list_of_points():
    pts = [
        {"x": 1, "y": 2},
        {"x": 3, "y": 4},
    ]
    assert deserialize(list[Point], pts) == [Point(1, 2), Point(3, 4)]


def test_deserialize_missing_field():
    pts = [
        {"x": 1, "y": 2},
        {"x": 3},
    ]
    with validation_errors({"[1]": "missing 1 required positional argument"}):
        deserialize(list[Point], pts)


def test_deserialize_multiple_errors():
    pt = {"x": [1], "y": [2]}
    with validation_errors(
        {
            "['x']": "for argument types [type[int], TrackingProxy[list]]",
            "['y']": "for argument types [type[int], TrackingProxy[list]]",
        }
    ):
        deserialize(Point, pt)


def test_primitive_int():
    assert deserialize(int, 3) == 3


def test_dict():
    assert deserialize(dict[str, int], {"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_deserialize_point_two_sources():
    assert deserialize(Point, Multiple([{"x": 1}, {"y": 2}])) == Point(1, 2)
