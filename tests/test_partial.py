from serieux.module import create
from serieux.partial import Partial, Sources, partials
from tests.common import Point

deserialize = create(partials).deserialize


def test_partial():
    one = deserialize(Partial[Point], {"x": 10})
    assert one.x == 10
    two = deserialize(Partial[Point], {"y": 30})
    assert two.y == 30


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
