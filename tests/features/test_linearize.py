from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Annotated, Optional, Union

from serieux.features.linearize import LinearChoice, LinearField, LinearTagged, linearize
from serieux.features.tagset import TagDict, TaggedUnion


@dataclass
class Person:
    name: str
    age: int


@dataclass
class Address:
    street: str
    city: str


@dataclass
class Employee:
    person: Person
    address: Address
    salary: float


@dataclass
class Cat:
    indoor: bool


@dataclass
class Dog:
    breed: str


@dataclass
class Pet:
    animal: TaggedUnion[Cat, Dog]
    name: str


@dataclass
class WithOptional:
    label: str
    person: Optional[Person]


@dataclass
class WithUnion:
    value: Union[int, str]


@dataclass
class WithDate:
    # date is StringModelizable
    born: date
    name: str


class Color(str, Enum):
    RED = "red"
    GREEN = "green"


@dataclass
class WithEnum:
    color: Color
    count: int


# ── flat struct ──────────────────────────────────────────────────────────────


def test_flat():
    items = linearize(Person)
    assert len(items) == 2
    assert all(isinstance(i, LinearField) for i in items)
    assert [i.path for i in items] == ["name", "age"]
    assert [i.type for i in items] == [str, int]


# ── nested struct is flattened ───────────────────────────────────────────────


def test_nested_flattened():
    items = linearize(Employee)
    assert all(isinstance(i, LinearField) for i in items)
    paths = [i.path for i in items]
    assert paths == ["person.name", "person.age", "address.street", "address.city", "salary"]


# ── tagged union → LinearTagged ──────────────────────────────────────────────


def test_tagged_union():
    items = linearize(Pet)
    tagged = [i for i in items if isinstance(i, LinearTagged)]
    assert len(tagged) == 1
    t = tagged[0]
    assert t.path == "animal"
    assert set(t.options.keys()) == {"cat", "dog"}


def test_tagged_union_options():
    items = linearize(Pet)
    t = next(i for i in items if isinstance(i, LinearTagged))

    cat_items = t.options["cat"].items
    assert len(cat_items) == 1
    assert isinstance(cat_items[0], LinearField)
    assert cat_items[0].path == "animal.indoor"
    assert cat_items[0].type is bool

    dog_items = t.options["dog"].items
    assert len(dog_items) == 1
    assert dog_items[0].path == "animal.breed"
    assert dog_items[0].type is str


def test_tagged_union_sibling_field():
    items = linearize(Pet)
    plain = [i for i in items if isinstance(i, LinearField)]
    assert any(i.path == "name" for i in plain)


# ── Optional[FieldModelizable] is flattened ──────────────────────────────────


def test_optional_struct_flattened():
    items = linearize(WithOptional)
    paths = [i.path for i in items]
    assert "label" in paths
    assert "person.name" in paths
    assert "person.age" in paths


# ── plain Union → LinearChoice ───────────────────────────────────────────────


def test_plain_union():
    items = linearize(WithUnion)
    assert len(items) == 1
    c = items[0]
    assert isinstance(c, LinearChoice)
    assert c.path == "value"
    assert len(c.options) == 2  # int branch, str branch


def test_plain_union_branches():
    c = linearize(WithUnion)[0]
    types = {items[0].type for items in c.options}
    assert types == {int, str}


# ── StringModelizable is treated as a leaf ───────────────────────────────────


def test_string_modelizable_leaf():
    items = linearize(WithDate)
    paths = [i.path for i in items]
    assert paths == ["born", "name"]
    assert all(isinstance(i, LinearField) for i in items)
    born = next(i for i in items if i.path == "born")
    assert born.type is date


# ── direct TagSet annotation → LinearTagged ──────────────────────────────────

vehicles = TagDict()


@vehicles.register("car")
@dataclass
class Car:
    horsepower: int


@vehicles.register("bike")
@dataclass
class Bike:
    gears: int


@dataclass
class Garage:
    vehicle: Annotated[object, vehicles]
    owner: str


def test_direct_tagset():
    items = linearize(Garage)
    tagged = [i for i in items if isinstance(i, LinearTagged)]
    assert len(tagged) == 1
    t = tagged[0]
    assert t.path == "vehicle"
    assert set(t.options.keys()) == {"car", "bike"}
    assert t.options["car"].items[0].path == "vehicle.horsepower"
    assert t.options["bike"].items[0].path == "vehicle.gears"


# ── Enum is a leaf ───────────────────────────────────────────────────────────


def test_enum_leaf():
    items = linearize(WithEnum)
    assert all(isinstance(i, LinearField) for i in items)
    color = next(i for i in items if i.path == "color")
    assert color.type is Color
