from typing import Any

import pytest

from serieux import Serieux
from serieux.ctx import Context
from serieux.exc import ValidationError
from serieux.features.autotag import AutoTagAny

from ..definitions import Point

srx = (Serieux + AutoTagAny)()
deserialize = srx.deserialize
serialize = srx.serialize
schema = srx.schema


class Pointato:
    x: int
    y: int


def test_serialize_point():
    ctx = Context()
    obj = Point(13, 14)
    result = serialize(object, obj, ctx)

    assert result == {"class": f"{Point.__module__}:Point", "x": 13, "y": 14}


def test_serialize_point_any():
    ctx = Context()
    obj = Point(13, 14)
    result = serialize(Any, obj, ctx)

    assert result == {"class": f"{Point.__module__}:Point", "x": 13, "y": 14}


def test_serialize_nested_class():
    class Nested(Point):
        pass

    ctx = Context()
    obj = Nested(44, 55)

    with pytest.raises(ValidationError, match="Only top-level symbols can be serialized"):
        serialize(object, obj, ctx)


def test_deserialize_point():
    ctx = Context()
    data = {"class": f"{Point.__module__}:Point", "x": 13, "y": 14}

    result = deserialize(object, data, ctx)
    expected = Point(13, 14)
    assert result == expected


def test_deserialize_point_any():
    ctx = Context()
    data = {"class": f"{Point.__module__}:Point", "x": 13, "y": 14}

    result = deserialize(Any, data, ctx)
    expected = Point(13, 14)
    assert result == expected


def test_deserialize_not_hit_unless_object():
    ctx = Context()
    data = {"class": f"{Point.__module__}:Point", "x": 13, "y": 14}

    # Passing Pointato instead of object should not trigger
    # the codepath for AutoTagAny
    with pytest.raises(ValidationError):
        deserialize(Pointato, data, ctx)


def test_deserialize_without_class():
    ctx = Context()
    data = {"x": 13, "y": 14}

    with pytest.raises(ValidationError, match="There must be a class reference to resolve"):
        deserialize(object, data, ctx)


def test_deserialize_vague_class():
    ctx = Context()
    data = {"class": "Point", "x": 13, "y": 14}
    with pytest.raises(ValidationError, match="Class reference must include module"):
        deserialize(object, data, ctx)


def test_deserialize_invalid_class_reference():
    ctx = Context()
    data = {"class": "invalid:reference", "value": "test"}

    with pytest.raises(ValidationError, match="ModuleNotFoundError"):
        deserialize(object, data, ctx)


def test_deserialize_bad_class_format():
    ctx = Context()
    data = {"class": "too:many:colons", "value": "test"}

    with pytest.raises(ValidationError, match="Bad format for class reference"):
        deserialize(object, data, ctx)


def test_serialize_int():
    ctx = Context()
    result = serialize(Any, 46, ctx)

    assert result == {
        "class": "builtins:int",
        "return": 46,
    }


def test_deserialize_int():
    ctx = Context()
    data = {"class": "builtins:int", "return": 42}
    result = deserialize(Any, data, ctx)
    assert result == 42
