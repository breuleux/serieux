from serieux.impl import schema as _schema

from .common import Defaults, Point


def schema(t, root=False, use_defs=False):
    return _schema(t).compile(root=root, use_defs=use_defs)


def test_schema_int():
    assert schema(int) == {"type": "integer"}


def test_schema_bool():
    assert schema(bool) == {"type": "boolean"}


def test_schema_str():
    assert schema(str) == {"type": "string"}


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
