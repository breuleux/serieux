from dataclasses import fields
from numbers import Number
from typing import TypeVar, Union

from serieux.utils import JSON, evaluate_hint as eh

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


def test_json_type_check():
    J = JSON[object]
    JL = JSON[list]
    for yes in [int, float, str, list[float], dict[str, str], dict[str, str | int]]:
        assert issubclass(yes, J)
    for no in [object, Point, dict[int, str], list]:
        assert not issubclass(no, J)
    assert not issubclass(dict[str, str], JL)
