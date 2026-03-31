from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pytest

from serieux import Serieux
from serieux.features.cli import CommandLineArguments, FromArguments, ParseError, parse_cli
from serieux.features.tagset import TaggedUnion

serieux = (Serieux + FromArguments)()
deserialize = serieux.deserialize


# ── fixture types ─────────────────────────────────────────────────────────────


@dataclass
class Person:
    # Name of the person
    name: str
    # Age of the person
    age: int


@dataclass
class Address:
    street: str
    city: str


@dataclass
class Employee:
    person: Person
    address: Address


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
class Command:
    # [positional]
    subcommand: TaggedUnion[Cat, Dog]
    owner: str


@dataclass
class Word:
    word: str = field(metadata={"positional": True})


@dataclass
class WithDate:
    born: date
    label: str


@dataclass
class WithBool:
    verbose: bool = False
    name: str = ""


# ── flat struct ───────────────────────────────────────────────────────────────


def test_flat():
    result = parse_cli(Person, ["--name", "Alice", "--age", "30"])
    assert result == {"name": "Alice", "age": 30}


def test_flat_via_deserialize():
    result = deserialize(Person, CommandLineArguments(["--name", "Bob", "--age", "25"]))
    assert result == Person(name="Bob", age=25)


# ── nested flatten ────────────────────────────────────────────────────────────


def test_nested_full_path():
    result = parse_cli(
        Employee,
        [
            "--person.name",
            "Alice",
            "--person.age",
            "40",
            "--address.street",
            "Main St",
            "--address.city",
            "Paris",
        ],
    )
    assert result == {
        "person": {"name": "Alice", "age": 40},
        "address": {"street": "Main St", "city": "Paris"},
    }


def test_nested_short_name_conflict():
    # Both person.name and... well, Employee has no top-level 'name', no conflict.
    # street and city are unambiguous short names.
    result = parse_cli(
        Employee,
        [
            "--person.name",
            "Alice",
            "--age",
            "40",
            "--street",
            "Main St",
            "--city",
            "Paris",
        ],
    )
    assert result["person"]["name"] == "Alice"
    assert result["address"]["city"] == "Paris"


# ── tagged union (option-style) ───────────────────────────────────────────────


def test_tagged_option():
    result = parse_cli(Pet, ["--animal", "cat", "--indoor", "--name", "Whiskers"])
    assert result == {"animal": {"$class": "cat", "indoor": True}, "name": "Whiskers"}


def test_tagged_option_dog():
    result = parse_cli(Pet, ["--animal", "dog", "--breed", "Labrador", "--name", "Rex"])
    assert result == {"animal": {"$class": "dog", "breed": "Labrador"}, "name": "Rex"}


def test_tagged_unknown_tag():
    with pytest.raises(ParseError, match="Unknown tag"):
        parse_cli(Pet, ["--animal", "fish"])


# ── tagged union (positional tag) ─────────────────────────────────────────────


def test_tagged_positional():
    result = parse_cli(Command, ["cat", "--indoor", "--owner", "Alice"])
    assert result == {"subcommand": {"$class": "cat", "indoor": True}, "owner": "Alice"}


def test_tagged_positional_dog():
    result = parse_cli(Command, ["dog", "--breed", "Poodle", "--owner", "Bob"])
    assert result == {"subcommand": {"$class": "dog", "breed": "Poodle"}, "owner": "Bob"}


# ── name conflict: priority after LinearTagged ────────────────────────────────


@dataclass
class Alpha:
    name: str
    score: int


@dataclass
class Beta:
    name: str
    rank: int


@dataclass
class Contest:
    entry: TaggedUnion[Alpha, Beta]


def test_tagged_name_priority():
    # Before tag selection, 'name' is ambiguous (alpha.name vs beta.name).
    # After 'alpha' is selected, 'name' maps unambiguously to alpha.name.
    result = parse_cli(Contest, ["--entry", "alpha", "--name", "Alice", "--score", "10"])
    assert result == {"entry": {"$class": "alpha", "name": "Alice", "score": 10}}


# ── positional field ──────────────────────────────────────────────────────────


def test_positional_field():
    result = parse_cli(Word, ["hello"])
    assert result == {"word": "hello"}


def test_positional_missing():
    with pytest.raises(ParseError):
        parse_cli(Person, ["unknown_positional"])


# ── unknown option ────────────────────────────────────────────────────────────


def test_unknown_option():
    with pytest.raises(ParseError, match="Unknown option"):
        parse_cli(Person, ["--unknown", "value"])


# ── bool fields ───────────────────────────────────────────────────────────────


def test_bool_flag_true():
    result = parse_cli(WithBool, ["--verbose"])
    assert result["verbose"] is True


def test_bool_flag_no():
    result = parse_cli(WithBool, ["--no-verbose"])
    assert result["verbose"] is False


# ── StringModelizable leaf (date) ─────────────────────────────────────────────


def test_string_modelizable():
    result = parse_cli(WithDate, ["--born", "2000-01-15", "--label", "bday"])
    assert result == {"born": "2000-01-15", "label": "bday"}


# ── full round-trip via deserialize ──────────────────────────────────────────


def test_roundtrip_tagged():
    result = deserialize(
        Pet, CommandLineArguments(["--animal", "dog", "--breed", "Husky", "--name", "Bolt"])
    )
    assert result == Pet(animal=Dog(breed="Husky"), name="Bolt")


def test_roundtrip_nested():
    result = deserialize(
        Employee,
        CommandLineArguments(
            [
                "--person.name",
                "Carol",
                "--person.age",
                "35",
                "--address.street",
                "Oak Ave",
                "--address.city",
                "Lyon",
            ]
        ),
    )
    assert result == Employee(
        person=Person(name="Carol", age=35), address=Address(street="Oak Ave", city="Lyon")
    )
