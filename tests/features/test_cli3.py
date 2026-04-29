from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from serieux import Serieux
from serieux.features.cli3 import ParseError, parse
from serieux.features.tagset import TaggedUnion

serieux = Serieux()


def check(command, expected, interface=None):
    if interface is None:
        interface = type(expected)
    args = command.split()
    flat = parse(interface, args)
    got = serieux.deserialize(interface, flat)
    assert got == expected


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
class Word:
    # [positional]
    word: str


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
    check("--name Alice --age 30", Person(name="Alice", age=30))


def test_flat_short_value():
    check("--name Bob --age 25", Person(name="Bob", age=25))


# ── nested flatten ────────────────────────────────────────────────────────────


def test_nested_full_path():
    check(
        "--person.name Alice --person.age 40 --address.street MainSt --address.city Paris",
        Employee(Person("Alice", 40), Address("MainSt", "Paris")),
    )


def test_nested_short_name():
    # street and city are unambiguous short names; person.age is unambiguous as --age.
    check(
        "--person.name Alice --age 40 --street MainSt --city Paris",
        Employee(Person("Alice", 40), Address("MainSt", "Paris")),
    )


# ── tagged union (option-style) ───────────────────────────────────────────────
# TaggedUnion linearizes a $class discriminator field; the option name is the
# field name (e.g. --animal), and the value is the tag ("cat" / "dog").
# Once selected, the branch-specific fields become available.


def test_tagged_option():
    check("--animal cat --indoor --name Whiskers", Pet(Cat(indoor=True), "Whiskers"))


def test_tagged_option_dog():
    check("--animal dog --breed Labrador --name Rex", Pet(Dog("Labrador"), "Rex"))


# ── tagged union (positional selector) ───────────────────────────────────────
# When the union field is [positional], the $class discriminator is also
# positional: the user supplies the tag ("cat" / "dog") as a bare argument.


@dataclass
class Command:
    # [positional]
    subcommand: TaggedUnion[Cat, Dog]
    owner: str


def test_tagged_positional():
    check("cat --indoor --owner Alice", Command(Cat(indoor=True), "Alice"))


def test_tagged_positional_dog():
    check("dog --breed Poodle --owner Bob", Command(Dog("Poodle"), "Bob"))


# ── plain union — structural discrimination ───────────────────────────────────
# Alpha | Beta (no tags): distinguished by unique fields (score vs rank).
# The discriminating field must come before shared latent fields.


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
    entry: Alpha | Beta


def test_discriminator_unlocks_shared_field():
    # 'score' is unique to Alpha; once provided, 'name' (shared/latent) becomes available.
    check("--score 10 --name Alice", Contest(Alpha("Alice", 10)))


def test_discriminator_unlocks_shared_field_beta():
    check("--rank 3 --name Bob", Contest(Beta("Bob", 3)))


# ── single-letter options use one dash ───────────────────────────────────────


@dataclass
class Flags:
    x: float
    y: float
    verbose: bool = False


def test_single_letter_option():
    check("-x 1.5 -y 2.5", Flags(x=1.5, y=2.5))


def test_single_letter_mixed_with_long():
    check("-x 3.0 -y 4.0 --verbose", Flags(x=3.0, y=4.0, verbose=True))


def test_compact_bool_flags():
    @dataclass
    class Multi:
        a: bool = False
        b: bool = False
        n: str = ""

    check("-ab", Multi(a=True, b=True))


def test_compact_bool_then_value():
    @dataclass
    class Multi:
        v: bool = False
        o: str = ""

    check("-vo out.txt", Multi(v=True, o="out.txt"))


def test_compact_value_inline():
    @dataclass
    class Multi:
        o: str = ""

    check("-oout.txt", Multi(o="out.txt"))


# ── positional field ──────────────────────────────────────────────────────────


def test_positional_field():
    check("hello", Word(word="hello"))


def test_positional_unexpected():
    with pytest.raises(ParseError, match="Unexpected positional"):
        parse(Person, ["unknown_positional"])


# ── unknown option ────────────────────────────────────────────────────────────


def test_unknown_option():
    with pytest.raises(ParseError, match="Unknown option"):
        parse(Person, ["--unknown", "value"])


def test_unknown_options_all_reported():
    # All unknown options are collected and reported together, not just the first.
    with pytest.raises(ParseError) as exc_info:
        parse(Person, ["--foo", "--bar", "--name", "Alice", "--age", "30"])
    assert "--foo" in str(exc_info.value)
    assert "--bar" in str(exc_info.value)


def test_prog_name_in_error():
    try:
        parse(Person, ["--unknown"], prog="myprog")
    except ParseError as e:
        assert "myprog" in str(e)


# ── bool fields ───────────────────────────────────────────────────────────────


def test_bool_flag_true():
    check("--verbose", WithBool(verbose=True))


def test_bool_flag_no():
    check("--no-verbose", WithBool(verbose=False))


# ── StringModelizable leaf (date) ─────────────────────────────────────────────


def test_string_modelizable():
    check("--born 2000-01-15 --label bday", WithDate(born=date(2000, 1, 15), label="bday"))


# ── full round-trip via deserialize ──────────────────────────────────────────


def test_roundtrip_tagged():
    check("--animal dog --breed Husky --name Bolt", Pet(Dog("Husky"), "Bolt"))


def test_roundtrip_nested():
    flat = parse(
        Employee,
        [
            "--person.name",
            "Carol",
            "--person.age",
            "35",
            "--address.street",
            "Oak Ave",
            "--address.city",
            "Lyon",
        ],
    )
    result = serieux.deserialize(Employee, flat)
    assert result == Employee(Person("Carol", 35), Address("Oak Ave", "Lyon"))


# ── plain union (Cat2 | Dog2) — discriminated by unique field presence ────────


@dataclass
class Cat2:
    indoor: bool = True
    age: int = 5


@dataclass
class Dog2:
    breed: str = "unknown"
    age: int = 3


@dataclass
class PetUnion:
    animal: Cat2 | Dog2


def test_choice_cat_branch():
    # --indoor discriminates Cat2; fires as a bool flag.
    check("--indoor --age 3", PetUnion(Cat2(indoor=True, age=3)))


def test_choice_dog_branch():
    check("--breed Poodle --age 5", PetUnion(Dog2(breed="Poodle", age=5)))


def test_choice_age_available_after_unlock():
    # 'age' is shared and becomes available only after a branch is selected.
    check("--indoor --age 7", PetUnion(Cat2(indoor=True, age=7)))
    check("--breed Lab --age 2", PetUnion(Dog2(breed="Lab", age=2)))


def test_branch_locks_out_sibling():
    # Once Cat2 is selected via --indoor, --breed is no longer available.
    with pytest.raises(ParseError, match="Unknown option"):
        parse(PetUnion, ["--indoor", "--breed", "Poodle"])


# ── undifferentiable union raises at linearize time ──────────────────────────


@dataclass
class ConflictingTypes:
    value: int | str


def test_undifferentiable_union_raises():
    with pytest.raises(Exception, match="differentiate"):
        parse(ConflictingTypes, [])
