from typing import Literal

import pytest
from ovld import Medley

from serieux import Serieux, dump, load, serialize
from serieux.ctx import AccessPath, Context
from serieux.exc import ValidationError

from .common import has_312_features, one_test_per_assert
from .definitions import Color, DIDHolder, DotDict, Level, LTHolder, Point


@one_test_per_assert
def test_serialize_scalars():
    assert serialize(0) == 0
    assert serialize(12) == 12
    assert serialize(-3.25) == -3.25
    assert serialize("flagada") == "flagada"
    assert serialize(True) is True
    assert serialize(False) is False
    assert serialize(None) is None


@one_test_per_assert
def test_serialize_scalars_conversion():
    assert serialize(float, 10) == 10.0


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


@has_312_features
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


def test_serialize_set():
    nums = {1, 2, 3, 4}
    assert serialize(set[int], nums) == [1, 2, 3, 4]


def test_serialize_frozenset():
    nums = frozenset({1, 2, 3, 4})
    assert serialize(frozenset[int], nums) == [1, 2, 3, 4]


def test_serialize_dict_subclass():
    data = DotDict(apple=3, banana=7)
    assert serialize(DotDict[str, int], data) == {"apple": 3, "banana": 7}


class Special(Medley):
    def serialize(self, typ: type[int], value: int, ctx: Context):
        return value * 10

    def serialize(self, typ: type[int], value: str, ctx: Context):
        return value * 2


def test_override():
    ss = (Serieux + Special)()
    assert ss.serialize(int, 3) == 30
    assert ss.serialize(int, "quack") == "quackquack"
    assert ss.serialize(list[int], [1, 2, 3]) == [10, 20, 30]
    assert ss.serialize(list[int], [1, "2", 3]) == [10, "22", 30]
    assert ss.serialize(Point, Point(8, 9)) == {"x": 80, "y": 90}
    assert ss.serialize(3) == 30


class quirkint(int):
    pass


class Quirky(Medley):
    def serialize(self, typ: type[int], value: quirkint, ctx: Context):
        return value * 10


def test_override_quirkint():
    ss = (Serieux + Quirky)()
    assert ss.serialize(int, 3) == 3
    assert ss.serialize(int, quirkint(3)) == 30
    assert ss.serialize(Point, Point(8, 9)) == {"x": 8, "y": 9}
    assert ss.serialize(Point, Point(quirkint(8), 9)) == {"x": 80, "y": 9}


class ExtraWeight(Context):
    weight: int


class WeightedImpl(Medley):
    def serialize(self, typ: type[int], value: int, ctx: ExtraWeight):
        return value + ctx.weight


def test_override_state():
    ss = (Serieux + WeightedImpl)()
    assert ss.serialize(int, 3) == 3
    assert ss.serialize(int, 3, ExtraWeight(10)) == 13
    assert ss.serialize(Point, Point(7, 8)) == {"x": 7, "y": 8}
    assert ss.serialize(Point, Point(7, 8), ExtraWeight(10)) == {"x": 17, "y": 18}


def test_serialize_enum():
    assert serialize(Color, Color.RED) == "red"
    assert serialize(list[Color], [Color.GREEN, Color.BLUE, Color.GREEN]) == [
        "green",
        "blue",
        "green",
    ]


def test_serialize_enum_int():
    assert serialize(Level, Level.MED) == 1
    assert serialize(list[Level], [Level.HI, Level.LO, Level.HI]) == [2, 0, 2]


def test_serialize_literal_enum():
    assert serialize(Literal["red", "green", "blue"], "red") == "red"
    with pytest.raises(
        ValidationError,
        match=r"'yellow' is not a valid option for typing.Literal\['red', 'green', 'blue'\]",
    ):
        serialize(Literal["red", "green", "blue"], "yellow")


###############
# Error tests #
###############


def test_error_basic():
    with pytest.raises(
        ValidationError, match=r"Cannot serialize object of type 'str' into expected type 'int'"
    ):
        serialize(int, "oh no")


def test_error_dataclass():
    with pytest.raises(
        ValidationError, match=r"Cannot serialize object of type 'str' into expected type 'int'"
    ):
        serialize(Point, Point(x=1, y="oops"), AccessPath())


@has_312_features
def test_error_serialize_tree():
    from .definitions_py312 import Tree

    tree = Tree(Tree("a", 2), "b")

    with pytest.raises(ValidationError, match=r"At path \.left\.right"):
        serialize(Tree[str], tree, AccessPath())


def test_error_serialize_list():
    li = [0, 1, 2, 3, "oops", 5, 6]

    with pytest.raises(ValidationError, match=r"At path .4"):
        serialize(list[int], li, AccessPath())


def test_error_serialize_list_of_lists():
    li = [[0, 1], [2, 3, "oops", 5, 6]]

    with pytest.raises(ValidationError, match=r"At path .1.2"):
        serialize(list[list[int]], li, AccessPath())


def test_dump_no_dest():
    pt = Point(1, 2)
    assert serialize(Point, pt) == dump(Point, pt)


def test_dump(tmp_path):
    dest = tmp_path / "point.yaml"
    pt = Point(1, 2)
    dump(Point, pt, dest=dest)
    assert load(Point, dest) == pt


def test_serialize_recursive_type():
    data = DIDHolder(
        did={
            "a": 1,
            "b": {
                "c": 2,
                "d": 3,
            },
        }
    )
    ser = serialize(DIDHolder, data)
    assert ser["did"] == data.did


def test_serialize_recursive_type_2():
    def p(x):
        return Point(x, x)

    data = LTHolder(lt=[p(1), [p(2), [p(3)], p(4)]])
    ser = serialize(LTHolder, data)
    assert ser["lt"] == [
        {"x": 1, "y": 1},
        [{"x": 2, "y": 2}, [{"x": 3, "y": 3}], {"x": 4, "y": 4}],
    ]
