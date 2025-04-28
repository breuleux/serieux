from __future__ import annotations

from dataclasses import dataclass

import pytest
from ovld import Dataclass, Dependent, Lambda, ovld
from ovld.dependent import Regexp

from serieux import deserialize, schema, serialize
from serieux.features.clargs import CommandLineArguments
from serieux.model import Field, Model


def _rgb_from_string(obj, cls):
    hex_str = obj.lstrip("#")
    red = int(hex_str[0:2], 16)
    green = int(hex_str[2:4], 16)
    blue = int(hex_str[4:6], 16)
    return cls(red=red, green=green, blue=blue)


@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @classmethod
    def serieux_deserialize(cls, obj, ctx, call_next):
        if isinstance(obj, str):
            return _rgb_from_string(obj, cls=RGB)
        else:
            return call_next(cls, obj, ctx)

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        if 0 <= obj.red <= 255:
            return f"#{obj.red:02x}{obj.green:02x}{obj.blue:02x}"
        else:
            return call_next(cls, obj, ctx)

    @classmethod
    def serieux_schema(cls, ctx, call_next):
        return {
            "oneOf": [
                {"type": "string", "pattern": r"^#[0-9a-fA-F]{6}$"},
                call_next(cls, ctx),
            ]
        }


def test_custom_deserialize():
    assert deserialize(RGB, "#ff00ff") == RGB(red=255, green=0, blue=255)
    assert deserialize(RGB, {"red": 255, "green": 100, "blue": 100}) == RGB(
        red=255, green=100, blue=100
    )


def test_custom_serialize():
    assert serialize(RGB, RGB(red=255, green=0, blue=255)) == "#ff00ff"
    assert serialize(RGB, RGB(red=1000, green=0, blue=0)) == {"red": 1000, "green": 0, "blue": 0}


def test_custom_schema():
    assert schema(RGB).compile(root=False) == {
        "oneOf": [
            {"type": "string", "pattern": r"^#[0-9a-fA-F]{6}$"},
            {
                "type": "object",
                "properties": {
                    "red": {"type": "integer"},
                    "green": {"type": "integer"},
                    "blue": {"type": "integer"},
                },
                "required": ["red", "green", "blue"],
                "additionalProperties": False,
            },
        ]
    }


@dataclass
class RGBO:
    red: int
    green: int
    blue: int

    @classmethod
    @ovld
    def serieux_deserialize(cls, obj: Regexp[r"^#[0-9a-fA-F]{6}$"], ctx, call_next):
        return _rgb_from_string(obj, cls=RGBO)

    @classmethod
    @ovld
    def serieux_serialize(
        cls, obj: Dependent[Dataclass, lambda rgb: 0 <= rgb.red <= 255], ctx, call_next
    ):
        assert 0 <= obj.red <= 255
        return f"#{obj.red:02x}{obj.green:02x}{obj.blue:02x}"


def test_custom_deserialize_o():
    assert deserialize(RGBO, "#ff00ff") == RGBO(red=255, green=0, blue=255)
    assert deserialize(RGBO, {"red": 255, "green": 100, "blue": 100}) == RGBO(
        red=255, green=100, blue=100
    )


def test_custom_serialize_o():
    assert serialize(RGBO, RGBO(red=255, green=0, blue=255)) == "#ff00ff"
    assert serialize(RGBO, RGBO(red=1000, green=0, blue=0)) == {"red": 1000, "green": 0, "blue": 0}


class RGBM:
    red: int
    green: int
    blue: int

    def __init__(self, red, green, blue):
        self.red = red
        self.green = green
        self.blue = blue

    @classmethod
    def serieux_model(cls, call_next):
        return Model(
            original_type=cls,
            fields=[
                Field(name="red", type=int, serialized_name="R"),
                Field(name="green", type=int, serialized_name="G"),
                Field(name="blue", type=int, serialized_name="B"),
            ],
            constructor=cls,
            from_string=Lambda("$from_string($obj, $t)", from_string=_rgb_from_string),
            regexp=r"^#[0-9a-fA-F]{6}$",
            string_description="A RGB color in hex, such as #ff0000",
        )


def test_custom_deserialize_m():
    obj = deserialize(RGBM, {"R": 30, "G": 100, "B": 200})
    assert isinstance(obj, RGBM)
    assert obj.red == 30 and obj.green == 100 and obj.blue == 200


def test_custom_deserialize_m_from_string():
    obj = deserialize(RGBM, "#ff0000")
    assert isinstance(obj, RGBM)
    assert obj.red == 255 and obj.green == 0 and obj.blue == 0


def test_custom_m_schema(file_regression):
    assert schema(RGBM).compile(root=False) == {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "R": {"type": "integer"},
                    "G": {"type": "integer"},
                    "B": {"type": "integer"},
                },
                "required": ["R", "G", "B"],
                "additionalProperties": False,
            },
            {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
        ]
    }


@dataclass
class HasColor:
    color: RGBM


def test_clargs_rgbm():
    clargs = CommandLineArguments(
        arguments=["--color", "#ff0000"],
        mapping={"": {"auto": True}},
    )
    obj = deserialize(HasColor, clargs)
    color = obj.color
    assert isinstance(color, RGBM)
    assert color.red == 255 and color.green == 0 and color.blue == 0


def test_clargs_bad_regexp():
    clargs = CommandLineArguments(
        arguments=["--color", "#ff00XX"],
        mapping={"": {"auto": True}},
    )
    with pytest.raises(SystemExit):
        deserialize(HasColor, clargs)
