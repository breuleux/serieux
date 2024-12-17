from serieux import model
from serieux.model import (
    Field,
    ListModel,
    MappingModel,
    StructuredModel,
    UnionModel,
)
from serieux.model import evaluate_hint as eh

from .common import Point


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
    assert model(eh(int | str)) == UnionModel(original_type=int | str, options=[int, str])


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
