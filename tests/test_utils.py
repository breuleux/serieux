from dataclasses import fields
from numbers import Number
from typing import TypeVar, Union

from serieux.utils import evaluate_hint as eh

from .common import Point, one_test_per_assert

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


def test_evaluate_hint_tree_parametric():
    from .definitions_py312 import Tree

    for field in fields(Tree):
        assert eh(field.type, Tree[float]) == Union[float, Tree[float]]
        assert eh(field.type, Tree[str]) == Union[str, Tree[str]]
