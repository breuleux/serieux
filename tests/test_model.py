from dataclasses import fields
from numbers import Number
from typing import TypeVar, Union

from serieux import model
from serieux.model import (
    Field,
    ListModel,
    MappingModel,
    StructuredModel,
    UnionModel,
)
from serieux.model import (
    evaluate_hint as eh,
)

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


def test_model_dict():
    assert model(dict[int, int]) == MappingModel(
        original_type=dict[int, int],
        builder=dict,
        extractor=dict,
        key_type=int,
        element_type=int,
    )


def test_model_list():
    assert model(list[float]) == ListModel(
        original_type=list[float],
        builder=list,
        extractor=list,
        element_type=float,
    )


def test_model_nested_list():
    assert model(list[list[float]]) == ListModel(
        original_type=list[list[float]],
        builder=list,
        extractor=list,
        element_type=ListModel(
            original_type=list[float],
            builder=list,
            extractor=list,
            element_type=float,
        ),
    )


def test_model_dataclass():
    assert model(Point) == StructuredModel(
        original_type=Point,
        builder=Point,
        fields={"x": Field(type=int), "y": Field(type=int)},
    )


def test_model_union():
    assert model(eh(int | str)) == UnionModel(
        original_type=int | str, options=[int, str]
    )


def test_model_tree():
    from .definitions import Tree

    m = model(Tree)
    assert m in m.fields["left"].type.options
    assert m in m.fields["right"].type.options


def test_model_tree_parametric():
    from .definitions_py312 import Tree

    m = model(Tree[float])
    assert m in m.fields["left"].type.options
    assert m in m.fields["right"].type.options
