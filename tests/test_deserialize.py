from datetime import date, datetime, timedelta
from pathlib import Path

from serieux import deserialize

from .common import Color, Defaults, Level, Point, Point3D, one_test_per_assert

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


@one_test_per_assert
def test_deserialize_union():
    assert deserialize(str | int, 3) == 3
    assert deserialize(str | int, "wow") == "wow"
    assert deserialize(Point | int, 3) == 3


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


def test_deserialize_date():
    assert deserialize(date, "2023-05-15") == date(2023, 5, 15)
    assert deserialize(list[date], ["2023-05-15", "2024-01-01"]) == [
        date(2023, 5, 15),
        date(2024, 1, 1),
    ]


def test_deserialize_datetime():
    assert deserialize(datetime, "2023-05-15T12:30:45") == datetime(2023, 5, 15, 12, 30, 45)
    assert deserialize(list[datetime], ["2023-05-15T12:30:45", "2024-01-01T00:00:00"]) == [
        datetime(2023, 5, 15, 12, 30, 45),
        datetime(2024, 1, 1, 0, 0, 0),
    ]


def test_deserialize_timedelta():
    assert deserialize(timedelta, "42s") == timedelta(seconds=42)
    assert deserialize(timedelta, "42500000us") == timedelta(seconds=42, microseconds=500000)
    assert deserialize(timedelta, "-10s") == timedelta(seconds=-10)
    assert deserialize(timedelta, "6h30m") == timedelta(hours=6, minutes=30)
    assert deserialize(timedelta, "+8d") == timedelta(days=8)
    assert deserialize(timedelta, "4.5d") == timedelta(days=4, seconds=60 * 60 * 12)
    assert deserialize(timedelta, "1d12h") == timedelta(days=1, hours=12)
    assert deserialize(timedelta, "36h") == timedelta(days=1, hours=12)
    assert deserialize(list[timedelta], ["30s", "5d"]) == [
        timedelta(seconds=30),
        timedelta(days=5),
    ]
