from dataclasses import dataclass
from types import NoneType
from typing import Literal

import pytest

from serieux import schema as _schema
from serieux.model import Extensible
from serieux.schema import AnnotatedSchema, Schema

from .common import has_312_features
from .definitions import Color, Defaults, LTHolder, Pig, Point


def schema(t, root=False, ref_policy="norepeat"):
    return _schema(t).compile(root=root, ref_policy=ref_policy)


def test_schema_hashable():
    sch1 = Schema(int)
    sch2 = Schema(int)
    assert sch1 == sch1
    assert not (sch1 == sch2)
    assert {sch1: 1, sch2: 2} == {sch1: 1, sch2: 2}


def test_schema_int():
    assert schema(int) == {"type": "integer"}


def test_schema_bool():
    assert schema(bool) == {"type": "boolean"}


def test_schema_str():
    assert schema(str) == {"type": "string"}


def test_schema_None():
    assert schema(NoneType) == {"type": "null"}


def test_schema_enum():
    assert schema(Color) == {"enum": ["red", "green", "blue"]}


def test_schema_literal():
    assert schema(Literal["red", "green", "blue"]) == {"enum": ["red", "green", "blue"]}


def test_schema_list():
    assert schema(list[int]) == {"type": "array", "items": {"type": "integer"}}


def test_schema_dict():
    assert schema(dict[str, float]) == {
        "type": "object",
        "additionalProperties": {"type": "number"},
    }


def test_schema_dict_non_str_keys():
    with pytest.raises(Exception, match="Cannot create a schema for dicts with non-string keys"):
        schema(dict[int, str])


def test_schema_nested():
    assert schema(dict[str, list[int]]) == {
        "type": "object",
        "additionalProperties": {"type": "array", "items": {"type": "integer"}},
    }


def test_schema_dataclass():
    assert schema(Point) == {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        "required": ["x", "y"],
        "additionalProperties": False,
    }


def test_schema_extensible_dataclass():
    assert schema(Extensible[Point]) == {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        "required": ["x", "y"],
        "additionalProperties": True,
    }


def test_schema_dataclass_2():
    assert schema(Defaults) == {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "cool": {"type": "boolean"},
        },
        "required": ["name"],
        "additionalProperties": False,
    }


@has_312_features
def test_schema_recursive():
    from .definitions_py312 import Tree

    assert schema(Tree[int]) == {
        "type": "object",
        "properties": {
            "left": {
                "oneOf": [
                    {"$ref": "#"},
                    {"type": "integer"},
                ]
            },
            "right": {
                "oneOf": [
                    {"$ref": "#"},
                    {"type": "integer"},
                ]
            },
        },
        "required": ["left", "right"],
        "additionalProperties": False,
    }


@has_312_features
def test_schema_recursive_policy_always():
    from .definitions_py312 import Tree

    assert schema(Tree[int], root=True, ref_policy="always") == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/Tree",
        "$defs": {
            "Tree": {
                "type": "object",
                "properties": {
                    "left": {
                        "oneOf": [
                            {"$ref": "#/$defs/Tree"},
                            {"type": "integer"},
                        ]
                    },
                    "right": {
                        "oneOf": [
                            {"$ref": "#/$defs/Tree"},
                            {"type": "integer"},
                        ]
                    },
                },
                "required": ["left", "right"],
                "additionalProperties": False,
            }
        },
    }


@has_312_features
def test_schema_recursive_policy_two_trees():
    from .definitions_py312 import Tree

    @dataclass
    class DoubleTree:
        it: Tree[int]
        st: Tree[str]

    assert schema(DoubleTree, root=True, ref_policy="always") == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/DoubleTree",
        "$defs": {
            "DoubleTree": {
                "type": "object",
                "properties": {
                    "it": {"$ref": "#/$defs/Tree"},
                    "st": {"$ref": "#/$defs/Tree2"},
                },
                "required": ["it", "st"],
                "additionalProperties": False,
            },
            "Tree": {
                "type": "object",
                "properties": {
                    "left": {
                        "oneOf": [
                            {"$ref": "#/$defs/Tree"},
                            {"type": "integer"},
                        ]
                    },
                    "right": {
                        "oneOf": [
                            {"$ref": "#/$defs/Tree"},
                            {"type": "integer"},
                        ]
                    },
                },
                "required": ["left", "right"],
                "additionalProperties": False,
            },
            "Tree2": {
                "type": "object",
                "properties": {
                    "left": {
                        "oneOf": [
                            {"$ref": "#/$defs/Tree2"},
                            {"type": "string"},
                        ]
                    },
                    "right": {
                        "oneOf": [
                            {"$ref": "#/$defs/Tree2"},
                            {"type": "string"},
                        ]
                    },
                },
                "required": ["left", "right"],
                "additionalProperties": False,
            },
        },
    }


@has_312_features
def test_schema_recursive_policy_never():
    from .definitions_py312 import Tree

    with pytest.raises(Exception, match="Recursive schema"):
        schema(Tree[int], root=True, ref_policy="never")


@dataclass
class TwoPoints:
    # First point
    a: Point
    # Second point
    b: Point


def test_schema_policy_never_minimal():
    never = schema(TwoPoints, ref_policy="never")
    minimal = schema(TwoPoints, ref_policy="minimal")
    assert (
        never
        == minimal
        == {
            "type": "object",
            "properties": {
                "a": {
                    "type": "object",
                    "description": "First point",
                    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                    "required": ["x", "y"],
                    "additionalProperties": False,
                },
                "b": {
                    "type": "object",
                    "description": "Second point",
                    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                    "required": ["x", "y"],
                    "additionalProperties": False,
                },
            },
            "required": ["a", "b"],
            "additionalProperties": False,
        }
    )


def test_schema_policy_norepeat():
    assert schema(TwoPoints, ref_policy="norepeat") == {
        "type": "object",
        "properties": {
            "a": {
                "type": "object",
                "description": "First point",
                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                "required": ["x", "y"],
                "additionalProperties": False,
            },
            "b": {
                "$ref": "#/properties/a",
                "description": "Second point",
            },
        },
        "required": ["a", "b"],
        "additionalProperties": False,
    }


def test_schema_policy_always():
    assert schema(TwoPoints, ref_policy="always") == {
        "$ref": "#/$defs/TwoPoints",
        "$defs": {
            "Point": {
                "type": "object",
                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                "required": ["x", "y"],
                "additionalProperties": False,
            },
            "TwoPoints": {
                "type": "object",
                "properties": {
                    "a": {"$ref": "#/$defs/Point", "description": "First point"},
                    "b": {"$ref": "#/$defs/Point", "description": "Second point"},
                },
                "required": ["a", "b"],
                "additionalProperties": False,
            },
        },
    }


def test_schema_descriptions():
    assert schema(Pig) == {
        "type": "object",
        "properties": {
            "pinkness": {"type": "number", "description": "How pink the pig is"},
            "weight": {"type": "number", "description": "Weight of the pig, in kilograms"},
            "beautiful": {
                "type": "boolean",
                "description": "Is the pig...\ntruly...\n...beautiful?",
                "default": True,
            },
        },
        "required": ["pinkness", "weight"],
        "additionalProperties": False,
    }


@pytest.mark.xfail
def test_schema_recursive_ltholder():
    assert schema(LTHolder) == {
        "type": "object",
        "properties": {
            "lt": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                            "required": ["x", "y"],
                            "additionalProperties": False,
                        },
                        {
                            "$ref": "#/properties/lt",
                        },
                    ]
                },
            },
        },
        "required": ["lt"],
        "additionalProperties": False,
    }


class AdditivePoint(Point):
    @classmethod
    def serieux_schema(cls, ctx, call_next):
        return AnnotatedSchema(
            parent=call_next(Point, ctx),
            properties={"more": {"type": "string"}},
            required=["more"],
        )


def test_schema_additive_point():
    assert schema(AdditivePoint) == {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "more": {"type": "string"},
        },
        "required": ["x", "y", "more"],
        "additionalProperties": False,
    }
