import pytest

from serieux.exc import ValidationError
from serieux.serialization import serialize, serialize_check

from .common import Point, one_test_per_assert


@one_test_per_assert
def test_serialize_scalars():
    assert serialize(0) == 0
    assert serialize(12) == 12
    assert serialize(-3.25) == -3.25
    assert serialize("flagada") == "flagada"
    assert serialize(True) is True
    assert serialize(False) is False
    assert serialize(None) is None


def test_serialize_point():
    pt = Point(1, 2)
    assert serialize(Point, pt) == {"x": 1, "y": 2}


def test_serialize_list_of_points():
    pts = [Point(1, 2), Point(3, 4)]
    assert serialize(list[Point], pts) == [
        {"x": 1, "y": 2},
        {"x": 3, "y": 4},
    ]


def test_serialize_dict_of_points():
    pts = {"p1": Point(1, 2), "p2": Point(3, 4)}
    assert serialize(dict[str, Point], pts) == {
        "p1": {"x": 1, "y": 2},
        "p2": {"x": 3, "y": 4},
    }


def test_serialize_tree():
    from .definitions_py312 import Tree

    tree = Tree(
        left=Tree(
            left=1,
            right=Tree(left=Tree(left=2, right=3), right=Tree(left=4, right=5)),
        ),
        right=Tree(left=Tree(left=6, right=7), right=8),
    )
    assert serialize(Tree[int], tree) == {
        "left": {
            "left": 1,
            "right": {
                "left": {"left": 2, "right": 3},
                "right": {"left": 4, "right": 5},
            },
        },
        "right": {"left": {"left": 6, "right": 7}, "right": 8},
    }


def test_error_serialize_tree():
    from .definitions_py312 import Tree

    tree = Tree(Tree(1, 2), 3)

    with pytest.raises(ValidationError, match=r"\.left\.left"):
        serialize_check(Tree[str], tree)


def test_error_serialize_list():
    li = [0, 1, 2, 3, "oops", 5, 6]

    with pytest.raises(ValidationError, match=r"At path \[4\]"):
        serialize_check(list[int], li)


def test_error_serialize_list_of_lists():
    li = [[0, 1], [2, 3, "oops", 5, 6]]

    with pytest.raises(ValidationError, match=r"At path \[1\]\[2\]"):
        serialize_check(list[list[int]], li)
