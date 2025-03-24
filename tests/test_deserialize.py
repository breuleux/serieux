from pathlib import Path

from serieux.deserialization import deserialize

from .common import Point, Point3D, one_test_per_assert

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
