import inspect
from datetime import date, datetime, timedelta

import pytest
from ovld import Medley

from serieux import Serieux, dump, load, serialize
from serieux.ctx import AccessPath, Context
from serieux.exc import ValidationError

from .common import has_312_features, one_test_per_assert
from .definitions import Color, Level, Point


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


SEP = """
======
"""


def getcodes(fn, *sigs):
    sigs = [(sig if isinstance(sig, tuple) else (sig,)) for sig in sigs]
    codes = [inspect.getsource(fn.resolve(*sig)) for sig in sigs]
    return SEP.join(codes)


def test_point_codegen(file_regression):
    code = getcodes(serialize, (type[Point], Point, Context))
    file_regression.check(code)


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


def test_special_serializer_codegen(file_regression):
    custom = (Serieux + Special)()
    code = getcodes(custom.serialize, (type[Point], Point, Context))
    file_regression.check(code)


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


def test_serialize_date():
    assert serialize(date, date(2023, 5, 15)) == "2023-05-15"
    assert serialize(list[date], [date(2023, 5, 15), date(2024, 1, 1)]) == [
        "2023-05-15",
        "2024-01-01",
    ]


def test_serialize_datetime():
    assert serialize(datetime, datetime(2023, 5, 15, 12, 30, 45)) == "2023-05-15T12:30:45"
    assert serialize(
        list[datetime], [datetime(2023, 5, 15, 12, 30, 45), datetime(2024, 1, 1, 0, 0, 0)]
    ) == ["2023-05-15T12:30:45", "2024-01-01T00:00:00"]


def test_serialize_timedelta():
    assert serialize(timedelta, timedelta(seconds=42)) == "42s"
    assert serialize(timedelta, timedelta(seconds=42, microseconds=500000)) == "42500000us"
    assert serialize(timedelta, timedelta(seconds=-10)) == "-10s"
    assert serialize(list[timedelta], [timedelta(seconds=30), timedelta(days=5)]) == [
        "30s",
        "432000s",
    ]


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
