import inspect
from dataclasses import dataclass

from ovld import extend_super

from serieux.serialization import Serializer, serialize
from serieux.state import State

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


SEP = """
======
"""


def getcodes(fn, *sigs):
    sigs = [(sig if isinstance(sig, tuple) else (sig,)) for sig in sigs]
    codes = [inspect.getsource(fn.resolve(*sig)) for sig in sigs]
    return SEP.join(codes)


def test_point_codegen(file_regression):
    code = getcodes(serialize, (type[Point], Point, State))
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


class SpecialSerializer(Serializer):
    @extend_super
    def transform(self, typ: type[int], value: int, state: State):
        return value * 10

    def transform(self, typ: type[int], value: str, state: State):
        return value * 2


def test_override():
    ss = SpecialSerializer()
    assert ss.transform(int, 3) == 30
    assert ss.transform(int, "quack") == "quackquack"
    assert ss.transform(list[int], [1, 2, 3]) == [10, 20, 30]
    assert ss.transform(list[int], [1, "2", 3]) == [10, "22", 30]
    assert ss.transform(Point, Point(8, 9)) == {"x": 80, "y": 90}
    assert ss.transform(3) == 30


def test_special_serializer_codegen(file_regression):
    code = getcodes(SpecialSerializer().transform, (type[Point], Point, State))
    file_regression.check(code)


class quirkint(int):
    pass


class QuirkySerializer(Serializer):
    @extend_super
    def transform(self, typ: type[int], value: quirkint, state: State):
        return value * 10


def test_override_quirkint():
    ss = QuirkySerializer()
    assert ss.transform(int, 3) == 3
    assert ss.transform(int, quirkint(3)) == 30
    assert ss.transform(Point, Point(8, 9)) == {"x": 8, "y": 9}
    assert ss.transform(Point, Point(quirkint(8), 9)) == {"x": 80, "y": 9}


@dataclass
class ExtraWeight(State):
    weight: int


class StatedSerializer(Serializer):
    @extend_super
    def transform(self, typ: type[int], value: int, state: ExtraWeight):
        return value + state.weight


def test_override_state():
    ss = StatedSerializer()
    assert ss.transform(int, 3) == 3
    assert ss.transform(int, 3, ExtraWeight(10)) == 13
    assert ss.transform(Point, Point(7, 8)) == {"x": 7, "y": 8}
    assert ss.transform(Point, Point(7, 8), ExtraWeight(10)) == {"x": 17, "y": 18}
