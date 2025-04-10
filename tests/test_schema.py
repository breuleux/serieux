from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytest

from serieux import schema as _schema

from .common import Color, Defaults, Pig, Point, has_312_features


def schema(t, root=False, ref_policy="norepeat"):
    return _schema(t).compile(root=root, ref_policy=ref_policy)


def test_schema_int():
    assert schema(int) == {"type": "integer"}


def test_schema_bool():
    assert schema(bool) == {"type": "boolean"}


def test_schema_str():
    assert schema(str) == {"type": "string"}


def test_schema_enum():
    assert schema(Color) == {"enum": ["red", "green", "blue"]}


def test_schema_date():
    assert schema(date) == {"type": "string", "format": "date"}


def test_schema_datetime():
    assert schema(datetime) == {"type": "string", "format": "date-time"}


def test_schema_timedelta():
    assert schema(timedelta) == {
        "type": "string",
        "pattern": r"^[+-]?(\d+[dhms]|\d+ms|\d+us)+$",
    }


def test_schema_list():
    assert schema(list[int]) == {"type": "array", "items": {"type": "integer"}}


def test_schema_dict():
    assert schema(dict[str, float]) == {
        "type": "object",
        "additionalProperties": {"type": "number"},
    }


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
            }
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
                },
                "b": {
                    "type": "object",
                    "description": "Second point",
                    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                    "required": ["x", "y"],
                },
            },
            "required": ["a", "b"],
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
            },
            "b": {
                "$ref": "#/properties/a",
                "description": "Second point",
            },
        },
        "required": ["a", "b"],
    }


def test_schema_policy_always():
    assert schema(TwoPoints, ref_policy="always") == {
        "$ref": "#/$defs/TwoPoints",
        "$defs": {
            "Point": {
                "type": "object",
                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                "required": ["x", "y"],
            },
            "TwoPoints": {
                "type": "object",
                "properties": {
                    "a": {"$ref": "#/$defs/Point", "description": "First point"},
                    "b": {"$ref": "#/$defs/Point", "description": "Second point"},
                },
                "required": ["a", "b"],
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
    }
