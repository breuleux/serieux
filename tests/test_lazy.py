from dataclasses import dataclass

import pytest

from serieux import Serieux
from serieux.exc import ValidationError
from serieux.features.lazy import DeepLazy, Lazy, LazyDeserialization, LazyProxy
from serieux.features.partial import Sources

from .definitions import Point

deserialize = (Serieux + LazyDeserialization)().deserialize


@dataclass(frozen=True)
class Person:
    name: str
    age: int

    def __post_init__(self):
        if self.age < 0:
            raise ValueError("Age cannot be negative!")


def test_lazy_proxy():
    lazy_value = LazyProxy(lambda: 42)

    assert lazy_value
    assert lazy_value == 42
    assert str(lazy_value) == "42"
    assert repr(lazy_value) == "42"


def test_lazy_arithmetic():
    lazy_a = LazyProxy(lambda: 10)
    lazy_b = LazyProxy(lambda: 5)
    lazy_c = LazyProxy(lambda: -3)

    assert lazy_a + lazy_b == 15
    assert lazy_a - lazy_b == 5
    assert lazy_a * lazy_b == 50
    assert lazy_a / lazy_b == 2.0
    assert lazy_a // lazy_b == 2
    assert lazy_a % lazy_b == 0
    assert lazy_a**lazy_b == 100000
    assert abs(lazy_c) == 3
    assert -lazy_c == 3
    assert +lazy_c == -3


def test_lazy_comparisons():
    lazy_value = LazyProxy(lambda: 42)
    assert lazy_value == 42
    assert lazy_value != 43
    assert lazy_value < 100
    assert lazy_value <= 42
    assert lazy_value > 0
    assert lazy_value >= 42


def test_lazy_list():
    lazy_list = LazyProxy(lambda: [1, 2, 3])

    assert len(lazy_list) == 3
    assert lazy_list[0] == 1
    assert list(lazy_list) == [1, 2, 3]
    assert 2 in lazy_list


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
