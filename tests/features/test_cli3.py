from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from ovld import ovld

from serieux import Serieux
from serieux.features.cli3 import ParseError, parse
from serieux.features.tagset import TaggedUnion

serieux = Serieux()


@ovld
def check(interface: type, command: str, *, error: str):
    args = command.split()
    with pytest.raises(Exception, match=error):
        flat = parse(interface, args)
        serieux.deserialize(interface, flat)


@ovld
def check(expected: Any, command: str):
    args = command.split()
    interface = type(expected)
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
class Menagerie:
    # [positional]
    pets: list[TaggedUnion[Cat, Dog]]


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
    check(Person(name="Alice", age=30), "--name Alice --age 30")


def test_flat_short_value():
    check(Person(name="Bob", age=25), "--name Bob --age 25")


# ── nested flatten ────────────────────────────────────────────────────────────


def test_nested_full_path():
    check(
        Employee(Person("Alice", 40), Address("MainSt", "Paris")),
        "--person.name Alice --person.age 40 --address.street MainSt --address.city Paris",
    )


def test_nested_short_name():
    # street and city are unambiguous short names; person.age is unambiguous as --age.
    check(
        Employee(Person("Alice", 40), Address("MainSt", "Paris")),
        "--person.name Alice --age 40 --street MainSt --city Paris",
    )


# ── tagged union (option-style) ───────────────────────────────────────────────
# TaggedUnion linearizes a $class discriminator field; the option name is the
# field name (e.g. --animal), and the value is the tag ("cat" / "dog").
# Once selected, the branch-specific fields become available.


def test_tagged_option():
    check(Pet(Cat(indoor=True), "Whiskers"), "--animal cat --indoor --name Whiskers")


def test_tagged_option_dog():
    check(Pet(Dog("Labrador"), "Rex"), "--animal dog --breed Labrador --name Rex")


# ── tagged union (positional selector) ───────────────────────────────────────
# When the union field is [positional], the $class discriminator is also
# positional: the user supplies the tag ("cat" / "dog") as a bare argument.


@dataclass
class Command:
    # [positional]
    subcommand: TaggedUnion[Cat, Dog]
    owner: str


def test_tagged_positional():
    check(Command(Cat(indoor=True), "Alice"), "cat --indoor --owner Alice")


def test_tagged_positional_dog():
    check(Command(Dog("Poodle"), "Bob"), "dog --breed Poodle --owner Bob")


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
    check(Contest(Alpha("Alice", 10)), "--score 10 --name Alice")


def test_discriminator_unlocks_shared_field_beta():
    check(Contest(Beta("Bob", 3)), "--rank 3 --name Bob")


# ── single-letter options use one dash ───────────────────────────────────────


@dataclass
class Flags:
    x: float
    y: float
    verbose: bool = False


def test_single_letter_option():
    check(Flags(x=1.5, y=2.5), "-x 1.5 -y 2.5")


def test_single_letter_mixed_with_long():
    check(Flags(x=3.0, y=4.0, verbose=True), "-x 3.0 -y 4.0 --verbose")


def test_compact_bool_flags():
    @dataclass
    class Multi:
        a: bool = False
        b: bool = False
        n: str = ""

    check(Multi(a=True, b=True), "-ab")


def test_compact_bool_then_value():
    @dataclass
    class Multi:
        v: bool = False
        o: str = ""

    check(Multi(v=True, o="out.txt"), "-vo out.txt")


def test_compact_value_inline():
    @dataclass
    class Multi:
        o: str = ""

    check(Multi(o="out.txt"), "-oout.txt")


# ── positional field ──────────────────────────────────────────────────────────


def test_positional_field():
    check(Word(word="hello"), "hello")


def test_positional_unexpected():
    check(Person, "unknown_positional", error="Unexpected positional")


# ── unknown option ────────────────────────────────────────────────────────────


def test_unknown_option():
    check(Person, "--unknown value", error="Unknown option")


def test_unknown_options_all_reported():
    check(Person, "--foo --bar --name Alice --age 30", error=".*--foo.*--bar.*")


def test_prog_name_in_error():
    try:
        parse(Person, ["--unknown"], prog="myprog")
    except ParseError as e:
        assert "myprog" in str(e)


# ── bool fields ───────────────────────────────────────────────────────────────


def test_bool_flag_true():
    check(WithBool(verbose=True), "--verbose")


def test_bool_flag_no():
    check(WithBool(verbose=False), "--no-verbose")


# ── StringModelizable leaf (date) ─────────────────────────────────────────────


def test_string_modelizable():
    check(WithDate(born=date(2000, 1, 15), label="bday"), "--born 2000-01-15 --label bday")


# ── full round-trip via deserialize ──────────────────────────────────────────


def test_roundtrip_tagged():
    check(Pet(Dog("Husky"), "Bolt"), "--animal dog --breed Husky --name Bolt")


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
    check(PetUnion(Cat2(indoor=True, age=3)), "--indoor --age 3")


def test_choice_dog_branch():
    check(PetUnion(Dog2(breed="Poodle", age=5)), "--breed Poodle --age 5")


def test_choice_age_available_after_unlock():
    # 'age' is shared and becomes available only after a branch is selected.
    check(PetUnion(Cat2(indoor=True, age=7)), "--indoor --age 7")
    check(PetUnion(Dog2(breed="Lab", age=2)), "--breed Lab --age 2")


def test_branch_locks_out_sibling():
    # Once Cat2 is selected via --indoor, --breed is disabled and the error says so.
    with pytest.raises(ParseError, match="disabled by"):
        parse(PetUnion, ["--indoor", "--breed", "Poodle"])


def test_latent_option_hints_at_prereq():
    # --breed on a TaggedUnion[Cat, Dog] is latent until --animal selects the branch.
    with pytest.raises(ParseError, match="requires"):
        parse(Pet, ["--breed", "Poodle"])


# ── undifferentiable union raises at linearize time ──────────────────────────


@dataclass
class ConflictingTypes:
    value: int | str


def test_undifferentiable_union_raises():
    with pytest.raises(Exception, match="differentiate"):
        parse(ConflictingTypes, [])


# ── multiple positional fields ────────────────────────────────────────────────


@dataclass
class Copy:
    # [positional]
    src: str
    # [positional]
    dst: str


def test_two_positionals():
    check(Copy(src="hello", dst="world"), "hello world")


def test_two_positionals_with_option():
    @dataclass
    class Move:
        # [positional]
        src: str
        # [positional]
        dst: str
        verbose: bool = False

    flat = parse(Move, ["a.txt", "--verbose", "b.txt"])
    got = serieux.deserialize(Move, flat)
    assert got == Move(src="a.txt", dst="b.txt", verbose=True)


def test_positional_tagged_union_then_positional():
    # Calculator: positional tag selects operation, then positional args fill the branch.
    # Add has positional x and y; the outer 'other' positional follows.
    from tests.features.test_linearize import Add, Calculator, Div

    r = parse(Calculator, ["add", "3.0", "4.5"])
    got = serieux.deserialize(Calculator, r)
    assert got == Calculator(operation=Add(x=3.0, y=4.5), other=0.0)

    r = parse(Calculator, ["div", "--num", "10.0", "--denom", "2.0"])
    got = serieux.deserialize(Calculator, r)
    assert got == Calculator(operation=Div(num=10.0, denom=2.0), other=0.0)


# ── list fields ───────────────────────────────────────────────────────────────


@dataclass
class Tags:
    words: list[str]


def test_list_str_repeated_option():
    check(Tags(words=["hello", "world", "foo"]), "--words hello --words world --words foo")


def test_list_str_single():
    check(Tags(words=["only"]), "--words only")


def test_list_tagged_union():
    @dataclass
    class Menagerie2:
        # not positional
        pets: list[TaggedUnion[Cat, Dog]]

    flat = parse(
        Menagerie2,
        ["--pets", "cat", "--indoor", "--pets", "dog", "--breed", "Husky"],
    )
    got = serieux.deserialize(Menagerie2, flat)
    assert got == Menagerie2(pets=[Cat(indoor=True), Dog(breed="Husky")])


def test_list_tagged_union_positional():
    flat = parse(
        Menagerie,
        ["cat", "--indoor", "dog", "--breed", "Husky"],
    )
    got = serieux.deserialize(Menagerie, flat)
    assert got == Menagerie(pets=[Cat(indoor=True), Dog(breed="Husky")])


###############
# Test errors #
###############


def test_wrong_branch():
    check(Menagerie, "cat --breed Siamese", error="--breed requires 'dog'")
