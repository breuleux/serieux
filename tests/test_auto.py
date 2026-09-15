from dataclasses import dataclass
from functools import partial
from typing import Annotated

import pytest

from serieux import deserialize, serialize
from serieux.auto import Auto, Call, MeldedCall
from serieux.exc import MissingFieldError, SchemaError, ValidationError
from serieux.features.tagset import TaggedUnion, tag_field
from serieux.model import constructed_type

from .definitions import Point


class Funky:
    def __init__(self, x: int, y: bool):
        self.marks = funky(x, y)


def funky(x: int, y: bool) -> str:
    return ("!" if y else ".") * x


def test_auto():
    funk = deserialize(Auto[Funky], {"x": 3, "y": True})
    assert funk.marks == "!!!"


def test_auto_from_init():
    funk = deserialize(Auto[Funky], {"x": 3, "y": True})
    assert funk.marks == "!!!"


def test_auto_callable():
    funk = deserialize(Auto[funky], {"x": 3, "y": True})
    assert funk() == "!!!"


def test_call_callable():
    funk = deserialize(Call[funky], {"x": 3, "y": True})
    assert funk == "!!!"


def test_call_on_type():
    with pytest.raises(TypeError, match=r"Call\[...\] should only wrap callables"):
        deserialize(Call[Funky], {"x": 3, "y": True})


def test_auto_not_serializable():
    with pytest.raises(SchemaError, match="does not specify how to serialize"):
        serialize(Auto[Funky], Funky(x=3, y=True))


def test_auto_serialize_partial():
    assert serialize(Auto[funky], partial(funky, x=3, y=True)) == {"x": 3, "y": True}


def test_auto_serialize_partial_positional():
    assert serialize(Auto[funky], partial(funky, 3, True)) == {"x": 3, "y": True}


def test_auto_serialize_partial_missing_required():
    with pytest.raises(MissingFieldError, match="'y'"):
        serialize(Auto[funky], partial(funky, x=3))


def test_auto_serialize_partial_skips_defaults():
    def g(x: int, z: int = 5) -> int:
        return x + z

    assert serialize(Auto[g], partial(g, x=3)) == {"x": 3}


def test_auto_serialize_partial_wrong_func():
    def other(x: int, y: bool) -> str:
        return ""

    with pytest.raises(ValidationError, match="Cannot serialize"):
        serialize(Auto[funky], partial(other, x=3, y=True))


def test_call_not_serializable_as_partial():
    with pytest.raises(ValidationError, match="Cannot serialize"):
        serialize(Call[funky], partial(funky, x=3, y=True))


def test_auto_class_not_serializable_as_partial():
    with pytest.raises(ValidationError, match="Cannot serialize"):
        serialize(Auto[Point], partial(Point, 1, 2))


def test_auto_no_interference():
    pt = serialize(Auto[Point], Point(1, 2))
    assert pt == {"x": 1, "y": 2}


def test_auto_func_lacks_annotations():
    def f(x, y: int) -> int:
        return x + y

    with pytest.raises(TypeError, match="lacks a type annotation"):
        deserialize(Auto[f], {"x": 1, "y": 2})


def add_them(x: int, y: int):
    return x + y


def mul_them(x: int, y: int) -> int:
    return x * y


def test_tagged_union():
    tu = TaggedUnion[Call[add_them], Call[mul_them]]

    result = deserialize(tu, {tag_field: "add_them", "x": 3, "y": 4})
    assert result == 7

    result = deserialize(tu, {tag_field: "mul_them", "x": 3, "y": 4})
    assert result == 12

    with pytest.raises(ValidationError, match="does not match expected tag"):
        deserialize(tu, {tag_field: "div_them", "x": 3, "y": 4})


def test_constructed_type():
    assert constructed_type(Call[mul_them]) is int
    with pytest.raises(TypeError, match="does not have a return type annotation"):
        constructed_type(Call[add_them])


@dataclass
class Person:
    name: str
    ha: str

    def laugh(self, n: int) -> str:
        return self.ha * n


def test_melded_call():
    cp = MeldedCall(Person, Person.laugh)
    assert cp(name="Alice", n=4, ha="ho") == "hohohoho"


def test_auto_method():
    hafn = deserialize(Auto[Person.laugh], {"name": "Bob", "ha": "hi", "n": 3})
    assert hafn() == "hihihi"


def test_auto_method_no_embed_self():
    hafn = deserialize(
        Annotated[Person.laugh, Call(embed_self=False)],
        {"self": {"name": "Bob", "ha": "hu"}, "n": 3},
    )
    assert hafn == "huhuhu"
