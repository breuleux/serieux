from __future__ import annotations

from dataclasses import dataclass

from ovld import Dataclass, Dependent, ovld
from ovld.dependent import Regexp

from serieux import deserialize, schema, serialize
from serieux.model import Field, Model


@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @classmethod
    def serieux_deserialize(cls, obj, ctx, call_next):
        if isinstance(obj, str):
            hex_str = obj.lstrip("#")
            red = int(hex_str[0:2], 16)
            green = int(hex_str[2:4], 16)
            blue = int(hex_str[4:6], 16)
            return RGB(red=red, green=green, blue=blue)
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
        hex_str = obj.lstrip("#")
        red = int(hex_str[0:2], 16)
        green = int(hex_str[2:4], 16)
        blue = int(hex_str[4:6], 16)
        return RGBO(red=red, green=green, blue=blue)

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
        return Model.make(
            original_type=cls,
            fields=[
                Field(name="red", type=int, serialized_name="R"),
                Field(name="green", type=int, serialized_name="G"),
                Field(name="blue", type=int, serialized_name="B"),
            ],
            constructor=cls,
        )


def test_custom_deserialize_m():
    obj = deserialize(RGBM, {"R": 30, "G": 100, "B": 200})
    assert isinstance(obj, RGBM)
    assert obj.red == 30 and obj.green == 100 and obj.blue == 200
