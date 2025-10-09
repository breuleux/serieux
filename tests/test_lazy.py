from dataclasses import dataclass

import pytest

from serieux import Serieux
from serieux.exc import ValidationError
from serieux.features.lazy import DeepLazy, Lazy, LazyDeserialization, LazyProxy
from serieux.features.partial import Sources

from .definitions import Point

srx = (Serieux + LazyDeserialization)()
deserialize = srx.deserialize
serialize = srx.serialize


@dataclass(frozen=True)
class Person:
    name: str
    age: int

    def __post_init__(self):
        if self.age < 0:
            raise ValidationError("Age cannot be negative!")


def test_lazy_object():
    person = Person(name="Bob", age=78)
    lazy_person = LazyProxy(lambda: person)

    assert person == lazy_person
    assert lazy_person.name == "Bob"
    assert lazy_person.age == 78
    assert hash(person) == hash(lazy_person)


def test_laziness():
    data = {"name": "Clara", "age": -10}
    lazy = deserialize(Lazy[Person], data)
    with pytest.raises(ValidationError, match="Age cannot be negative"):
        lazy.age


def test_deep_laziness():
    data = [
        {"name": "Alice", "age": 18},
        {"name": "Bob", "age": -78},
        {"name": "Clara", "age": 10},
    ]
    lazy = deserialize(Lazy[list[Person]], data)
    with pytest.raises(ValidationError, match="Age cannot be negative"):
        lazy[0].name

    deep_lazy = deserialize(DeepLazy[list[Person]], data)
    assert deep_lazy[0].name == "Alice"
    deep_lazy[1]  # No attributes fetched, so nothing happens
    with pytest.raises(ValidationError, match="Age cannot be negative"):
        deep_lazy[1].name
    assert deep_lazy[2].name == "Clara"


@dataclass
class ContainsLazy:
    normal: str
    pt: Lazy[Point]


def test_lazy_partial_invalid():
    result = deserialize(ContainsLazy, Sources({"normal": "hello", "pt": {"x": 1}}))
    assert result.normal == "hello"
    with pytest.raises(ValidationError):
        result.pt.x


def test_lazy_partial():
    result = deserialize(
        ContainsLazy,
        Sources(
            {"normal": "hello", "pt": {"x": 1}},
            {"pt": {"y": 18}},
        ),
    )
    assert result.normal == "hello"
    assert result.pt.x == 1
    assert result.pt.y == 18
    assert type(result.pt.y) is int


def test_lazy_callable():
    def add(a, b):
        return a + b

    lazy_func = LazyProxy(lambda: add)

    assert lazy_func(1, 2) == 3
    assert lazy_func(a=1, b=2) == 3

    # Test with a class that implements __call__
    class Adder:
        def __init__(self, base):
            self.base = base

        def __call__(self, x):
            return self.base + x

    lazy_adder = LazyProxy(lambda: Adder(10))
    assert lazy_adder(5) == 15


def test_lazyproxy_serialize():
    lazy_point = LazyProxy(lambda: Point(1, 2))
    serialized = serialize(Point, lazy_point)
    assert serialized == {"x": 1, "y": 2}
