import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

from serieux import Serieux
from serieux.ctx import Patcher
from serieux.exc import NotGivenError, ValidationError
from serieux.features.interpol import VariableInterpolation, Variables
from serieux.features.partial import Sources
from tests.definitions import Country

deserialize = (Serieux + VariableInterpolation)().deserialize

datapath = Path(__file__).parent.parent / "data"


@dataclass
class Player:
    name: str
    nickname: str
    number: int


@dataclass
class Team:
    name: str
    rank: int
    forward: Player
    defender: Player
    goalie: Player


def test_simple_interpolate():
    data = {"name": "Robert", "nickname": "${name}", "number": 1}
    assert deserialize(Player, data, Variables()) == Player(
        name="Robert",
        nickname="Robert",
        number=1,
    )


def test_relative():
    data = {
        "name": "Team ${forward.nickname}",
        "rank": 7,
        "forward": {"name": "Igor", "nickname": "${.name}", "number": 1},
        "defender": {"name": "Robert", "nickname": "${.name}${.name}", "number": 2},
        "goalie": {"name": "Harold", "nickname": "Roldy", "number": "${..rank}"},
    }
    assert deserialize(Team, data, Variables()) == Team(
        name="Team Igor",
        rank=7,
        forward=Player(name="Igor", nickname="Igor", number=1),
        defender=Player(name="Robert", nickname="RobertRobert", number=2),
        goalie=Player(name="Harold", nickname="Roldy", number=7),
    )


def test_chain():
    data = [
        {"name": "Aaron", "nickname": "Ho", "number": 1},
        {"name": "Barbara", "nickname": "${0.nickname}s", "number": 2},
        {"name": "Cornelius", "nickname": "${1.nickname}s", "number": 3},
        {"name": "Dominic", "nickname": "${2.nickname}s", "number": 4},
    ]
    players = deserialize(list[Player], data, Variables())
    assert str(players[1].nickname) == "Hos"
    assert str(players[2].nickname) == "Hoss"
    assert str(players[3].nickname) == "Hosss"


def test_refer_to_object():
    data = [{"name": "Jon", "nickname": "Pork", "number": 1}, "${0}"]
    players = deserialize(list[Player], data, Variables())
    assert players[0] == players[1]


@dataclass
class DateMix:
    sdate: str
    ddate: date


def test_further_conversion():
    data = {"sdate": "2025-05-01", "ddate": "${sdate}"}
    dm = deserialize(DateMix, data, Variables())
    assert dm.ddate == date(2025, 5, 1)


def test_further_conversion_2():
    data = {"sdate": "2025-05", "ddate": "${sdate}-01"}
    dm = deserialize(DateMix, data, Variables())
    assert dm.ddate == date(2025, 5, 1)


def test_deadlock():
    data = {"name": "${nickname}", "nickname": "${name}", "number": 1}
    player = deserialize(Player, data, Variables())
    with pytest.raises(Exception, match="Deadlock"):
        player.name == "x"


def test_env():
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TESTOTRON", "123")
        data = {"name": "Jon", "nickname": "Jonathan", "number": "${env:TESTOTRON}"}
        player = deserialize(Player, data, Variables())
        assert player.name == "Jon"
        assert player.number == 123


def test_env_types():
    vars = Variables(environ={"BOOL": "yes"})
    vars = Variables(
        environ={
            "BOOL": "yes",
            "INT": "42",
            "FLOAT": "3.14",
            "STR": "hello",
            "LIST": "a,b,c",
            "BOOL_FALSE": "no",
        }
    )

    assert deserialize(bool, "${env:BOOL}", vars) is True
    assert deserialize(int, "${env:INT}", vars) == 42
    assert deserialize(float, "${env:FLOAT}", vars) == 3.14
    assert deserialize(str, "${env:STR}", vars) == "hello"
    assert deserialize(list[str], "${env:LIST}", vars) == ["a", "b", "c"]
    assert deserialize(bool, "${env:BOOL_FALSE}", vars) is False


def test_invalid_boolean():
    with pytest.raises(ValidationError, match="Cannot convert 'invalid' to boolean"):
        deserialize(bool, "${env:INVALID_BOOL}", Variables(environ={"INVALID_BOOL": "invalid"}))


def test_unsupported_resolver():
    with pytest.raises(
        ValidationError,
        match="Cannot resolve 'unknown:xyz' because the 'unknown' resolver is not defined",
    ):
        deserialize(str, "${unknown:xyz}", Variables())


def test_not_given():
    with pytest.raises(NotGivenError, match="Environment variable 'MISSING' is not defined"):
        deserialize(str, "${env:MISSING}", Variables())


@dataclass
class Fool:
    name: str
    iq: int = 100


def test_not_given_ignore():
    srcs = Sources({"name": "John"}, {"iq": "${env:INTEL}"})

    d = deserialize(Fool, srcs, Variables())
    assert d.iq == 100

    d = deserialize(Fool, srcs, Variables(environ={"INTEL": "31"}))
    assert d.iq == 31


_canada = str(datapath / "canada.yaml")
_france = str(datapath / "france.yaml")


@mock.patch.dict(os.environ, {"FILOU": _canada})
def test_resolve_envfile():
    canada = deserialize(Country, "${envfile:FILOU}", Variables())
    assert canada.capital == "Ottawa"


@mock.patch.dict(os.environ, {"FILOU": f"{_canada}, {_france}"})
def test_resolve_envfile_two_files():
    canada = deserialize(Country, "${envfile:FILOU}", Variables())
    assert canada.capital == "Ottawa"
    assert [c.name for c in canada.citizens] == ["Olivier", "Abraham", "Jeannot"]


def test_resolve_envfile_not_given():
    canada = deserialize(Country, Sources(Path(_canada), "${envfile:FILOU}"), Variables())
    assert canada.capital == "Ottawa"


@dataclass
class Person:
    name: str
    age: int
    mad: bool


def _prompter(prompts):
    def resolve(ctx, prompt):
        assert prompt in prompts
        return prompts[prompt]

    return resolve


def test_resolve_prompt():
    value = deserialize(
        int,
        "${prompt:Enter your age}",
        Variables(prompt_function=_prompter({"Enter your age": "42"})),
    )
    assert value == 42


def test_resolve_prompt_boolean():
    value = deserialize(
        bool,
        "${prompt:Are you sure?}",
        Variables(prompt_function=_prompter({"Are you sure?": "yes"})),
    )
    assert value is True


def test_resolve_prompt_string():
    value = deserialize(
        str,
        "${prompt:What is your name?}",
        Variables(prompt_function=_prompter({"What is your name?": "John Doe"})),
    )
    assert value == "John Doe"


TEST_YAML = """
name: "${prompt:Enter your name}"
age: "${prompt:Enter your age}"
mad: "${prompt:Is the person mad?}"
"""

MODIFIED_YAML = """
name: "John Doe"
age: 42
mad: true
"""


def test_prompt_with_patcher(tmp_path):
    # Create a YAML file with a prompt directive
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(TEST_YAML)

    # Create a prompter that returns fixed values
    prompter = _prompter(
        {"Enter your name": "John Doe", "Enter your age": "42", "Is the person mad?": "yes"}
    )

    # Deserialize with Patcher
    ctx = Variables(prompt_function=prompter) + Patcher()
    result = deserialize(Person, yaml_file, ctx)

    # Verify the deserialized result
    assert result == Person(name="John Doe", age=42, mad=True)

    # Apply patches
    ctx.apply_patches()

    # Verify the file was modified
    modified_content = yaml_file.read_text()
    assert modified_content == MODIFIED_YAML
