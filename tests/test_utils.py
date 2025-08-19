from dataclasses import fields
from numbers import Number
from typing import TypeVar, Union

from serieux.utils import JSON, JSONLike, evaluate_hint as eh

from .common import has_312_features, one_test_per_assert
from .definitions import Point

T1 = TypeVar("T1")
T2 = TypeVar("T2")


@one_test_per_assert
def test_evaluate_hint():
    assert eh("str") is str
    assert eh(list["Point"], Point) == list[Point]
    assert eh(Union[int, "str"]) == int | str
    assert eh("int | str") == int | str


@one_test_per_assert
def test_evaluate_hint_generics():
    assert eh(dict[T1, T2]) == dict[T1, T2]
    assert eh(dict[T1, T2], typesub={T1: int}) == dict[int, T2]
    assert eh(dict[T1, T2], typesub={T2: int}) == dict[T1, int]
    assert eh(dict[T1, T2], typesub={T1: int, T2: str}) == dict[int, str]
    assert eh(dict[T2, T1], typesub={T1: int, T2: str}) == dict[str, int]


def test_evaluate_hint_tree():
    from .definitions import Tree

    for field in fields(Tree):
        assert eh(field.type, Tree) == Number | Tree


@has_312_features
def test_evaluate_hint_tree_parametric():
    from .definitions_py312 import Tree

    for field in fields(Tree):
        assert eh(field.type, Tree[float]) == Union[float, Tree[float]]
        assert eh(field.type, Tree[str]) == Union[str, Tree[str]]


def test_json_like():
    J = JSONLike[object]
    JL = JSONLike[list]
    for yes in [int, float, str, list[float], dict[str, str], dict[str, str | int]]:
        assert issubclass(yes, J)
    for no in [object, Point, dict[int, str], list]:
        assert not issubclass(no, J)
    assert not issubclass(dict[str, str], JL)


@one_test_per_assert
def test_json():
    assert isinstance(1, JSON)
    assert isinstance(3.14, JSON)
    assert isinstance("hello", JSON)
    assert isinstance([1, 2, 3], JSON)
    assert isinstance({"a": 1, "b": [2, {"z": 3}]}, JSON)
    assert isinstance([True, False, None], JSON)


class NotJson:
    pass


@one_test_per_assert
def test_not_json():
    assert not isinstance({"a": NotJson()}, JSON)
    assert not isinstance([1, 2, NotJson(), 3], JSON)
    assert not isinstance(NotJson(), JSON)
    assert not isinstance(set([1, 2, 3]), JSON)
    assert not isinstance((1, 2, 3), JSON)
    assert not isinstance(object(), JSON)
