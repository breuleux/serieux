from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from types import NoneType
from typing import Annotated, Optional, Union

import pytest
from ovld import ovld, recurse

from serieux.features.linearize import (
    GroupState,
    LinearField,
    LinearGroup,
    LinearState as LS,
    linearize,
)
from serieux.features.tagset import TagDict, TaggedUnion


@ovld
def sexp(lin: LinearField):
    if ul := lin.unlock:
        rval = f"<{ul.group.identifier}/{ul.choice_id}>{lin.identifier}"
        if ul.expected_value:
            rval = f"{rval}={ul.expected_value}"
        if lin.type is NoneType:
            rval += "-"
        return rval
    else:
        return lin.identifier


@ovld
def sexp(lin: LinearGroup):
    og = {f"{k}/{i}": recurse(e) for k, v in lin.option_groups.items() for i, e in enumerate(v)}
    return [recurse(x) for x in lin.fields] + ([og] if og else [])


@ovld
def sexp(lin: list):
    return [recurse(x) for x in lin]


@dataclass
class Person:
    """A person."""

    name: str
    age: int


@dataclass
class Job:
    """A job."""

    name: str
    salary: int


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
    """Meower."""

    indoor: bool


@dataclass
class Dog:
    """Woofer."""

    breed: str


@dataclass
class Pet:
    """Pet!"""

    # The animal
    animal: TaggedUnion[Cat, Dog]
    # The animal's name
    name: str


@dataclass
class WithOptional:
    label: str
    person: Optional[Person]


@dataclass
class WithDate:
    # date is StringModelizable
    born: date
    name: str


@dataclass
class Thing:
    color: str
    size: str


@dataclass
class HasThings:
    things: set[Thing]


@dataclass
class Capharnaum:
    elements: list[TaggedUnion[Cat, Dog]]


@dataclass
class MultiU:
    # A person... or a job!
    u1: Person | Job
    # A cat... or a DOG!
    u2: Cat | Dog


class Color(str, Enum):
    RED = "red"
    GREEN = "green"


@dataclass
class WithEnum:
    color: Color
    count: int


def test_flat():
    items = linearize(Person)
    assert sexp(items) == ["name", "age"]
    assert [i.type for i in items.fields] == [str, int]


def test_nested_flattened():
    items = linearize(Employee)
    assert sexp(items) == ["person.name", "person.age", "address.street", "address.city", "salary"]


def test_tagged_union():
    items = linearize(Pet)
    assert sexp(items) == [
        "<animal/0>animal.$class=cat",
        "<animal/1>animal.$class=dog",
        "name",
        {
            "animal/0": ["animal.indoor"],
            "animal/1": ["animal.breed"],
        },
    ]


def test_optional_struct_flattened():
    items = linearize(WithOptional)
    assert sexp(items) == [
        "label",
        "<person/0>person.name",
        "<person/0>person.age",
        {"person/0": []},
    ]


def test_indistinguishable_union():
    with pytest.raises(Exception, match="Cannot differentiate"):
        linearize(Union[int, str])


def test_union_struct():
    items = linearize(Union[Person, Address])
    assert sexp(items) == [
        "</0>name",
        "</0>age",
        "</1>street",
        "</1>city",
        {"/0": [], "/1": []},
    ]


def test_union_struct_overlap():
    items = linearize(Union[Person, Job])
    assert sexp(items) == [
        "</0>age",
        "</1>salary",
        {"/0": ["name"], "/1": ["name"]},
    ]


def test_multiple_union():
    items = linearize(MultiU)
    assert sexp(items) == [
        "<u1/0>u1.age",
        "<u1/1>u1.salary",
        "<u2/0>u2.indoor",
        "<u2/1>u2.breed",
        {"u1/0": ["u1.name"], "u1/1": ["u1.name"], "u2/0": [], "u2/1": []},
    ]


def test_union_struct_leaf():
    items = linearize(Union[Person, str])
    assert sexp(items) == ["</0>name", "</0>age", "</1>", {"/0": [], "/1": []}]


def test_string_modelizable_leaf():
    items = linearize(WithDate)
    assert sexp(items) == ["born", "name"]
    assert items.fields[0].type is date


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
    assert sexp(items) == [
        "<vehicle/0>vehicle.$class=car",
        "<vehicle/1>vehicle.$class=bike",
        "owner",
        {"vehicle/0": ["vehicle.horsepower"], "vehicle/1": ["vehicle.gears"]},
    ]


def test_list():
    items = linearize(HasThings)
    assert sexp(items) == ["things.#.color", "things.#.size"]


def test_list_of_tagged():
    items = linearize(Capharnaum)
    assert sexp(items) == [
        "<elements.#/0>elements.#.$class=cat",
        "<elements.#/1>elements.#.$class=dog",
        {"elements.#/0": ["elements.#.indoor"], "elements.#/1": ["elements.#.breed"]},
    ]


def test_enum_leaf():
    items = linearize(WithEnum)
    assert sexp(items) == ["color", "count"]
    assert items.fields[0].type is Color


def test_documentation():
    items = linearize(Pet)
    docs = {
        sexp(f): {
            "doc": f.doc,
            "enclosing": f.enclosing_doc,
            "parent": f.parent.doc,
        }
        for f in items.fields
    }
    assert docs == {
        "<animal/0>animal.$class=cat": {
            "doc": "Meower.",
            "enclosing": "Meower.",
            "parent": "The animal",
        },
        "<animal/1>animal.$class=dog": {
            "doc": "Woofer.",
            "enclosing": "Woofer.",
            "parent": "The animal",
        },
        "name": {
            "doc": "The animal's name",
            "enclosing": "Pet!",
            "parent": "Pet!",
        },
    }
    assert items.group_field.doc == "Pet!"


def _state(gs):
    return {field: state.state for field, state in gs.state.items()}


def test_groupstate_simple():
    items = linearize(Employee)
    assert sexp(items) == ["person.name", "person.age", "address.street", "address.city", "salary"]
    [name, age, street, city, salary] = items.fields

    gs = GroupState(items)
    assert _state(gs) == {
        name: LS.AVAILABLE,
        age: LS.AVAILABLE,
        street: LS.AVAILABLE,
        city: LS.AVAILABLE,
        salary: LS.AVAILABLE,
    }

    assert gs.advance(street) == street.identifier

    assert _state(gs) == {
        name: LS.AVAILABLE,
        age: LS.AVAILABLE,
        street: LS.FILLED,
        city: LS.AVAILABLE,
        salary: LS.AVAILABLE,
    }

    assert gs.advance(name) == name.identifier
    assert gs.advance(age) == age.identifier
    assert gs.advance(street) is False
    assert gs.advance(city) == city.identifier
    assert gs.advance(salary) == salary.identifier

    assert _state(gs) == {
        name: LS.FILLED,
        age: LS.FILLED,
        street: LS.FILLED,
        city: LS.FILLED,
        salary: LS.FILLED,
    }


def test_groupstate_tagged_union():
    items = linearize(Pet)
    trig_cat, trig_dog, name = items.fields
    ag = items.option_groups["animal"]
    [indoors] = ag[0].fields
    [breed] = ag[1].fields

    gs = GroupState(items)
    assert _state(gs) == {
        trig_cat: LS.AVAILABLE,
        trig_dog: LS.AVAILABLE,
        name: LS.AVAILABLE,
        indoors: LS.LATENT,
        breed: LS.LATENT,
    }

    assert gs.advance(trig_cat) == trig_cat.identifier
    assert gs.advance(trig_dog) is False

    assert _state(gs) == {
        trig_cat: LS.FILLED,
        trig_dog: LS.UNAVAILABLE,
        name: LS.AVAILABLE,
        indoors: LS.AVAILABLE,
        breed: LS.UNAVAILABLE,
    }

    assert gs.advance(indoors) == indoors.identifier

    assert _state(gs) == {
        trig_cat: LS.FILLED,
        trig_dog: LS.UNAVAILABLE,
        name: LS.AVAILABLE,
        indoors: LS.FILLED,
        breed: LS.UNAVAILABLE,
    }

    assert gs.advance(indoors) is False


def test_groupstate_list():
    items = linearize(HasThings)
    [color, size] = items.fields

    gs = GroupState(items)
    assert _state(gs) == {
        color: LS.AVAILABLE,
        size: LS.AVAILABLE,
    }

    assert gs.advance(color) == "things.0.color"

    assert _state(gs) == {
        color: LS.ADVANCE,
        size: LS.AVAILABLE,
    }

    assert gs.advance(color) == "things.1.color"

    assert _state(gs) == {
        color: LS.ADVANCE,
        size: LS.AVAILABLE,
    }

    assert gs.advance(size) == "things.1.size"

    assert _state(gs) == {
        color: LS.ADVANCE,
        size: LS.ADVANCE,
    }


def test_groupstate_list_of_tagged():
    items = linearize(Capharnaum)
    trig_cat, trig_dog = items.fields
    ((gcat, gdog),) = items.option_groups.values()
    [indoor] = gcat.fields
    [breed] = gdog.fields

    gs = GroupState(items)
    assert _state(gs) == {
        trig_cat: LS.AVAILABLE,
        trig_dog: LS.AVAILABLE,
        indoor: LS.LATENT,
        breed: LS.LATENT,
    }

    assert gs.advance(trig_cat) == "elements.0.$class"

    assert _state(gs) == {
        trig_cat: LS.ADVANCE,
        trig_dog: LS.ADVANCE,
        indoor: LS.AVAILABLE,
        breed: LS.LATENT,
    }

    assert gs.advance(trig_dog) == "elements.1.$class"

    assert _state(gs) == {
        trig_cat: LS.ADVANCE,
        trig_dog: LS.ADVANCE,
        indoor: LS.LATENT,
        breed: LS.AVAILABLE,
    }

    assert gs.advance(breed) == "elements.1.breed"

    assert _state(gs) == {
        trig_cat: LS.ADVANCE,
        trig_dog: LS.ADVANCE,
        indoor: LS.LATENT,
        breed: LS.FILLED,
    }

    assert gs.advance(breed) is False
