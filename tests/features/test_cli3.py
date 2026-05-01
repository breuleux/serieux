from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from ovld import ovld

from serieux import Serieux
from serieux.features.cli3 import CommandLineArguments, FromArguments
from serieux.features.tagset import TaggedUnion

serieux = Serieux() + FromArguments()


@ovld
def check(interface: type, command: str, *, error: str):
    args = command.split()
    with pytest.raises(Exception, match=error):
        serieux.deserialize(interface, CommandLineArguments(args))


@ovld
def check(expected: Any, command: str):
    args = command.split()
    interface = type(expected)
    got = serieux.deserialize(interface, CommandLineArguments(args))
    assert got == expected


########
# Flat #
########


@dataclass
class Person:
    """A person."""

    # Name of the person
    # [alias: -n]
    name: str
    # Age of the person
    # [alias: -a]
    age: int


def test_flat_use():
    check(Person(name="Alice", age=30), "--name Alice --age 30")
    check(Person(name="Alice", age=30), "--name Alice --age 30")
    check(Person(name="Bob", age=25), "--name Bob --age 25")
    check(Person(name="Charles", age=70), "--age 70 --name Charles")
    check(Person(name="Alice", age=30), "-n Alice -a 30")


def test_flat_errors():
    check(Person, "xyz", error="Unexpected positional")
    check(Person, "--unknown value", error="Unknown option")
    check(Person, "--name David", error="Missing required field 'age'")
    check(Person, "--age 888", error="Missing required field 'name'")
    check(Person, "--name --age 3", error="Missing value for argument 'name'")
    check(
        Person,
        "--name David --age blah",
        error="invalid literal for int.. with base 10: 'blah'",
    )
    check(Person, "", error="Missing required field 'name'")


def test_flat_multiple_errors():
    # All unexpected options should be mentioned
    check(Person, "--foo --bar --name Alice --age 30", error=".*--foo.*--bar.*")


#################
# Boolean flags #
#################


@dataclass
class TickTock:
    # [alias: -i]
    tick: bool = True
    # [alias: -o]
    tock: bool = False


def test_boolean_flags():
    check(TickTock(True, False), "")
    check(TickTock(True, False), "--tick")
    check(TickTock(True, True), "--tock")
    check(TickTock(True, True), "--tick --tock")
    check(TickTock(False, False), "--no-tick")
    check(TickTock(True, False), "--no-tock")
    check(TickTock(False, False), "--no-tick --no-tock")


def test_boolean_flags_short():
    check(TickTock(True, True), "-i -o")
    check(TickTock(True, True), "-io")
    check(TickTock(True, True), "-oi")
    check(TickTock(False, False), "--no-i --no-o")


##########
# Nested #
##########


@dataclass
class Address:
    street: str
    city: str


@dataclass
class Employee:
    person: Person
    address: Address


def test_nested():
    check(
        Employee(Person("Alice", 40), Address("MainSt", "Paris")),
        "--person.name Alice --person.age 40 --address.street MainSt --address.city Paris",
    )
    check(
        Employee(Person("Alice", 40), Address("MainSt", "Paris")),
        "--name Alice --age 40 --street MainSt --city Paris",
    )


###############
# TaggedUnion #
###############


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


def test_tagged_union():
    check(Pet(Cat(indoor=True), "Whiskers"), "--animal cat --indoor --name Whiskers")
    check(Pet(Dog("Labrador"), "Rex"), "--animal dog --breed Labrador --name Rex")
    check(Pet(Dog("Labrador"), "Rex"), "--name Rex --animal dog --breed Labrador")
    check(Pet(Dog("Labrador"), "Rex"), "--animal dog --name Rex --breed Labrador")


def test_tagged_union_errors():
    check(Pet, "--breed Retriever", error="requires --animal='dog'")


##########################
# Positional TaggedUnion #
##########################


@dataclass
class Pet2:
    # [positional]
    animal: TaggedUnion[Cat, Dog]
    owner: str


def test_tagged_union_positional():
    check(Pet2(Cat(indoor=True), "Alice"), "cat --indoor --owner Alice")
    check(Pet2(Dog("Poodle"), "Bob"), "dog --breed Poodle --owner Bob")
    check(Pet2(Dog("Poodle"), "Bob"), "--owner Bob dog --breed Poodle")
    check(Pet2(Dog("Poodle"), "Bob"), "dog --owner Bob --breed Poodle")


def test_tagged_union_positional_errors():
    check(Pet2, "--breed Retriever", error="requires 'dog'")


#########
# Union #
#########


@dataclass
class NameParts:
    first: str
    last: str


@dataclass
class Fullname:
    name: str


@dataclass
class IdNumber:
    id: int


@dataclass
class Worker:
    worker: NameParts | Fullname | IdNumber


def test_union():
    check(Worker(NameParts("Alice", "Rheault")), "--last Rheault --first Alice")
    check(Worker(NameParts("Alice", "Rheault")), "--first Alice --last Rheault")
    check(Worker(Fullname("AliceRheault")), "--name AliceRheault")
    check(Worker(IdNumber(333)), "--id 333")


def test_union_errors():
    check(Worker, "--name BobBob --id 123", error="--id was disabled by --worker.name")
    check(Worker, "--id 234 --name BobBob", error="--name was disabled by --worker.id")


######################
# Union with overlap #
######################


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


def test_union_with_overlap():
    check(Contest(Alpha("Alice", 10)), "--score 10 --name Alice")
    check(Contest(Beta("Bob", 3)), "--rank 3 --name Bob")


def test_union_with_overlap_errors():
    check(Contest, "--name Charles", error="requires --entry.score")


##############
# Positional #
##############


def test_positional():
    @dataclass
    class Word:
        # [positional]
        word: str

    check(Word(word="hello"), "hello")


def test_two_positionals():
    @dataclass
    class Copy:
        # [positional]
        src: str
        # [positional]
        dst: str

    check(Copy(src="hello", dst="world"), "hello world")


def test_two_positionals_with_option():
    @dataclass
    class Move:
        # [positional]
        src: str
        # [positional]
        dst: str
        verbose: bool = False

    check(
        Move(src="a.txt", dst="b.txt", verbose=True),
        "a.txt --verbose b.txt",
    )


def test_positional_tagged_union_then_positional():
    from tests.features.test_linearize import Add, Calculator, Div

    check(Calculator(operation=Add(x=3.0, y=4.5), other=0.0), "add 3.0 4.5")
    check(Calculator(operation=Div(num=10.0, denom=2.0), other=0.0), "div --num 10.0 --denom 2.0")


#########
# Lists #
#########


def test_list_str_repeated_option():
    @dataclass
    class Tags:
        words: list[str]

    check(Tags(words=["hello", "world", "foo"]), "--words hello --words world --words foo")
    check(Tags(words=["only"]), "--words only")


def test_list_tagged_union():
    @dataclass
    class Menagerie:
        # not positional
        pets: list[TaggedUnion[Cat, Dog]]

    check(
        Menagerie(pets=[Cat(indoor=True), Dog(breed="Husky")]),
        "--pets cat --indoor --pets dog --breed Husky",
    )


def test_list_tagged_union_positional():
    @dataclass
    class Menagerie:
        # [positional]
        pets: list[TaggedUnion[Cat, Dog]]

    check(
        Menagerie(pets=[Cat(indoor=True), Dog(breed="Husky")]),
        "cat --indoor dog --breed Husky",
    )


#################
# Miscellaneous #
#################


def test_compact_bool_then_value():
    @dataclass
    class Args:
        v: bool = False
        o: str = ""

    check(Args(v=True, o="out.txt"), "-vo out.txt")


def test_compact_value_inline():
    @dataclass
    class Args:
        o: str = ""

    check(Args(o="out.txt"), "-oout.txt")


# def test_prog_name_in_error():
#     try:
#         parse(Person, ["--unknown"], prog="myprog")
#     except ParseError as e:
#         assert "myprog" in str(e)


# def test_undifferentiable_union_raises():
#     @dataclass
#     class ConflictingTypes:
#         value: int | str

#     with pytest.raises(Exception, match="differentiate"):
#         parse(ConflictingTypes, [])


def test_string_modelizable():
    @dataclass
    class WithDate:
        born: date
        label: str

    check(WithDate(born=date(2000, 1, 15), label="bday"), "--born 2000-01-15 --label bday")


def test_option_override():
    @dataclass
    class WithOption:
        # [option: -o]
        output: str
        verbose: bool = False

    # -o is the only valid name; --output and --with-option.output are not.
    check(WithOption(output="out.txt"), "-o out.txt")
    check(WithOption, "--output x", error="Unknown option")
