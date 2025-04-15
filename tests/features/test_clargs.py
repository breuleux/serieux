from dataclasses import dataclass, field
from datetime import date
from enum import Enum

import pytest

from serieux import deserialize
from serieux.ctx import Context
from serieux.features.clargs import CommandLineArguments
from serieux.features.tagged import Tagged

from ..definitions import Point


@dataclass
class Person:
    # Name of the person
    name: str

    # Age of the person
    age: int


@dataclass
class HeroProfile:
    beautiful: bool = True
    has_superpowers: bool = False
    loves_adventure: bool = True


class Material(str, Enum):
    WOOD = "wood"
    BRICK = "brick"
    CONCRETE = "concrete"
    STEEL = "steel"
    GLASS = "glass"


@dataclass
class House:
    # Date at which the house was built
    built: date

    # Building material
    material: Material


def test_simple():
    result = deserialize(
        Person,
        CommandLineArguments(["--name", "Jon", "--age", "27"]),
        Context(),
    )
    assert result == Person(name="Jon", age=27)


def test_help(capsys, file_regression):
    with pytest.raises(SystemExit):
        deserialize(Person, CommandLineArguments(["-h"]), Context())
    captured = capsys.readouterr()
    file_regression.check(captured.out + "\n=====\n" + captured.err)


def test_booleans():
    def f(*argv):
        return deserialize(HeroProfile, CommandLineArguments(argv), Context())

    assert f() == HeroProfile(True, False, True)
    assert f("--no-beautiful") == HeroProfile(False, False, True)
    assert f("--no-beautiful", "--has-superpowers", "--no-loves-adventure") == HeroProfile(
        False, True, False
    )


def test_misc_types():
    def f(*argv):
        return deserialize(House, CommandLineArguments(argv), Context())

    assert f("--built", "2025-01-01", "--material", "brick") == House(
        built=date(2025, 1, 1), material=Material.BRICK
    )
    with pytest.raises(SystemExit):
        f("--built", "2025-01-01", "--material", "invalid")


@dataclass
class Eat:
    """Stuffing your mouth."""

    food: str

    def do(self):
        return f"I eat {self.food}"


@dataclass
class Sleep:
    """Stuffing your brain with dreams."""

    hours: int

    def do(self):
        return f"I sleep {self.hours} hours"


@dataclass
class Act:
    """Do stuff!"""

    # What to do
    command: Tagged[Eat, "eat"] | Tagged[Sleep, "sleep"]  # noqa: F821

    # Do we do it fast?
    fast: bool = field(default=False, metadata={"argparse": {"alias": "-f"}})

    def text(self):
        return self.command.do() + (" fast" if self.fast else "")


@dataclass
class TalkingPoint(Point):
    def text(self):
        return f"Hi I am at ({self.x}, {self.y})"


def test_subcommands():
    def do(*args):
        result = deserialize(
            Tagged[Eat, "eat"] | Tagged[Sleep, "sleep"],
            CommandLineArguments(args),
            Context(),
        )
        return result.do()

    assert do("eat", "--food", "jam") == "I eat jam"
    assert do("sleep", "--hours", "8") == "I sleep 8 hours"


def test_args_plus_subcommands():
    def text(*args):
        result = deserialize(Act, CommandLineArguments(args), Context())
        return result.text()

    assert text("--fast", "eat", "--food", "jam") == "I eat jam fast"
    assert text("-f", "eat", "--food", "jam") == "I eat jam fast"
    assert text("sleep", "--hours", "8") == "I sleep 8 hours"


def test_subcommands_help(capsys, file_regression):
    with pytest.raises(SystemExit):
        deserialize(Act, CommandLineArguments(["-h"]), Context())
    captured = capsys.readouterr()
    file_regression.check(captured.out + "\n=====\n" + captured.err)


def test_subcommand_help(capsys, file_regression):
    with pytest.raises(SystemExit):
        deserialize(Act, CommandLineArguments(["eat", "-h"]), Context())
    captured = capsys.readouterr()
    file_regression.check(captured.out + "\n=====\n" + captured.err)


def test_sub_subcommands():
    def text(*args):
        result = deserialize(
            Tagged[Act, "act"] | Tagged[TalkingPoint, "point"],
            CommandLineArguments(args),
            Context(),
        )
        return result.text()

    assert text("act", "eat", "--food", "jam") == "I eat jam"
    assert text("act", "--fast", "eat", "--food", "jam") == "I eat jam fast"
    assert text("act", "sleep", "--hours", "8") == "I sleep 8 hours"
    assert text("point", "-x", "1", "-y", "2") == "Hi I am at (1, 2)"


@dataclass
class Word:
    word: str = field(metadata={"argparse": {"positional": True}})


def test_positional():
    result = deserialize(Word, CommandLineArguments(["amazing"]), Context())
    assert result == Word(word="amazing")


@dataclass
class Duck:
    quacks: int = field(metadata={"argparse": {"option": "-q"}})


def test_replace_option():
    result = deserialize(Duck, CommandLineArguments(["-q", "7"]), Context())
    assert result == Duck(quacks=7)
