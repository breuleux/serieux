import pytest
from ovld import extend_super

from serieux.exc import ValidationError
from serieux.serialization import Serializer, serialize, serialize_check

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


def test_error_basic():
    with pytest.raises(ValidationError, match=r"No way to serialize"):
        serialize_check(int, "oh no")


def test_error_serialize_tree():
    from .definitions_py312 import Tree

    tree = Tree(Tree("a", 2), "b")

    with pytest.raises(ValidationError, match=r"At path \.left\.right"):
        serialize_check(Tree[str], tree)


def test_error_serialize_list():
    li = [0, 1, 2, 3, "oops", 5, 6]

    with pytest.raises(ValidationError, match=r"At path \[4\]"):
        serialize_check(list[int], li)


def test_error_serialize_list_of_lists():
    li = [[0, 1], [2, 3, "oops", 5, 6]]

    with pytest.raises(ValidationError, match=r"At path \[1\]\[2\]"):
        serialize_check(list[list[int]], li)


class SpecialSerializer(Serializer):
    @extend_super
    def serialize_sync(self, typ: type[int], value: int):
        return value * 10

    def serialize_sync(self, typ: type[int], value: str):
        return value * 2


def test_override():
    ss = SpecialSerializer()
    assert ss.serialize_sync(int, 3) == 30
    assert ss.serialize_sync(int, "quack") == "quackquack"
    assert ss.serialize_sync(list[int], [1, 2, 3]) == [10, 20, 30]
    assert ss.serialize_sync(list[int], [1, "2", 3]) == [10, "22", 30]
    assert ss.serialize_sync(Point, Point(8, 9)) == {"x": 80, "y": 90}
    assert ss.serialize(3) == 30
