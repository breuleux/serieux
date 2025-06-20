from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Literal

import pytest

from serieux import Serieux
from serieux.ctx import Context
from serieux.exc import ValidationError
from serieux.features.clargs import CommandLineArguments, parse_cli
from serieux.features.fromfile import FromFileExtra, WorkingDirectory
from serieux.features.interpol import Environment
from serieux.features.tagged import Tagged, TaggedUnion

from ..definitions import Defaults, Job, Point, Worker

deserialize = (Serieux + FromFileExtra)().deserialize

datapath = Path(__file__).parent.parent / "data"


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


def test_variables():
    result = deserialize(
        Person,
        CommandLineArguments(["--name", "Jon", "--age", "${env:AGE}"]),
        Environment(environ={"AGE": "33"}),
    )
    assert result == Person(name="Jon", age=33)


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


def test_lists():
    def f(*argv):
        return deserialize(Defaults, CommandLineArguments(argv), Context())

    assert f("--name", "Tyrone") == Defaults(name="Tyrone", aliases=[], cool=False)
    assert f("--name", "Tyrone", "--aliases", "Ty", "Ro", "Ne") == Defaults(
        name="Tyrone", aliases=["Ty", "Ro", "Ne"], cool=False
    )


@dataclass
class Defaults2:
    name: str
    aliases: list[str] = field(default_factory=list, metadata={"option": "-a", "action": "append"})
    cool: bool = field(default=False, kw_only=True)


def test_lists_append():
    def f(*argv):
        return deserialize(Defaults2, CommandLineArguments(argv), Context())

    assert f("--name", "Tyrone") == Defaults2(name="Tyrone", aliases=[], cool=False)
    assert f("--name", "Tyrone", "-a", "Ty", "-a", "Ro", "-a", "Ne") == Defaults2(
        name="Tyrone", aliases=["Ty", "Ro", "Ne"], cool=False
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

    food: str = None

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
    command: TaggedUnion[Eat, Sleep]  # noqa: F821

    # Do we do it fast?
    fast: bool = field(default=False, metadata={"alias": "-f"})

    def text(self):
        return self.command.do() + (" fast" if self.fast else "")


@dataclass
class TalkingPoint(Point):
    def text(self):
        return f"Hi I am at ({self.x}, {self.y})"


def test_subcommands():
    def do(*args):
        result = deserialize(
            TaggedUnion[Eat, Sleep],
            CommandLineArguments(args),
            Context(),
        )
        return result.do()

    assert do("eat", "--food", "jam") == "I eat jam"
    assert do("sleep", "--hours", "8") == "I sleep 8 hours"


def test_single_subcommand():
    def text(*args):
        result = deserialize(
            Tagged[Eat],
            CommandLineArguments(args),
            Context(),
        )
        return result.do()

    assert text("eat", "--food", "jam") == "I eat jam"


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
class Eater:
    command: TaggedUnion[Eat]

    def text(self):
        return self.command.do() + " only"


def test_one_sub_subcommands():
    def text(*args):
        result = deserialize(
            TaggedUnion[Eater],
            CommandLineArguments(args),
            Context(),
        )
        return result.text()

    assert text("eater", "eat", "--food", "jam") == "I eat jam only"


@dataclass
class Word:
    word: str = field(metadata={"positional": True})


def test_positional():
    result = deserialize(Word, CommandLineArguments(["amazing"]), Context())
    assert result == Word(word="amazing")


@dataclass
class Sentence:
    # [nargs: *]
    sentence: str


def test_nargs_on_str():
    result = deserialize(Sentence, CommandLineArguments(["--sentence", "Hi", "guys!"]), Context())
    assert result == Sentence(sentence="Hi guys!")


@dataclass
class Duck:
    # [option: -q]
    quacks: int


def test_replace_option():
    result = deserialize(Duck, CommandLineArguments(["-q", "7"]), Context())
    assert result == Duck(quacks=7)


def test_mapping():
    cla = CommandLineArguments(
        ["--tit", "Inspector", "--yar", "35000", "-n", "Gunther"],
        mapping={"job.title": "--tit", "job.yearly_pay": "--yar", "name": "-n"},
    )
    result = deserialize(Worker, cla, Context())
    assert result == Worker(name="Gunther", job=Job(title="Inspector", yearly_pay=35000))


def test_recursive():
    cla = CommandLineArguments(
        ["--name", "Gunther", "--title", "Inspector", "--yearly-pay", "35000"]
    )
    result = deserialize(Worker, cla, WorkingDirectory(datapath))
    assert result == Worker(name="Gunther", job=Job(title="Inspector", yearly_pay=35000))


def test_mapping_with_config_file():
    def deserialize_cli(args):
        cla = CommandLineArguments(
            args,
            mapping={"": {"auto": True, "option": "--config"}},
        )
        return deserialize(Worker, cla, WorkingDirectory(datapath))

    result = deserialize_cli(["--config", "worker.yaml"])
    assert result == Worker(name="Hagrid", job=Job(title="Vagrant", yearly_pay=10))

    result = deserialize_cli(["--config", "worker.yaml", "--title", "Inspector"])
    assert result == Worker(name="Hagrid", job=Job(title="Inspector", yearly_pay=10))

    with pytest.raises(ValidationError, match="there was no such file"):
        deserialize_cli(["--config", "whatever.yaml", "--title", "Inspector"])

    result = deserialize_cli(
        ["--config", '{"name":"Hagrid","job":{"title":"Vagrant","yearly_pay":10}}']
    )
    assert result == Worker(name="Hagrid", job=Job(title="Vagrant", yearly_pay=10))


def test_parse_cli():
    result = parse_cli(
        root_type=Worker,
        mapping={
            "name": "-n",
            "job.title": "--tit",
            "job.yearly_pay": "--yar",
        },
        argv=["-n", "Gunther", "--tit", "Inspector", "--yar", "35000"],
        description="W O R K",
    )
    worker = deserialize(Worker, result, Context())
    assert worker == Worker(name="Gunther", job=Job(title="Inspector", yearly_pay=35000))

    result = parse_cli(
        root_type=Worker,
        argv=["--name", "Gunther", "--title", "Inspector", "--yearly-pay", "35000"],
    )
    worker = deserialize(Worker, result, Context())
    assert worker == Worker(name="Gunther", job=Job(title="Inspector", yearly_pay=35000))


@dataclass
class Konfig:
    mode: Literal["dev", "prod", "test"]
    level: Literal["debug", "info", "warning", "error"]


def test_parse_literal():
    result = parse_cli(
        root_type=Konfig,
        argv=["--mode", "dev", "--level", "debug"],
    )
    config = deserialize(Konfig, result, Context())
    assert config == Konfig(mode="dev", level="debug")

    result = parse_cli(
        root_type=Konfig,
        argv=["--mode", "prod", "--level", "info"],
    )
    config = deserialize(Konfig, result, Context())
    assert config == Konfig(mode="prod", level="info")

    with pytest.raises(SystemExit):
        parse_cli(
            root_type=Konfig,
            argv=["--mode", "invalid", "--level", "debug"],
        )

    with pytest.raises(SystemExit):
        parse_cli(
            root_type=Konfig,
            argv=["--mode", "dev", "--level", "invalid"],
        )
