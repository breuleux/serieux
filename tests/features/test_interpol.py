import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import NoneType
from unittest import mock

import pytest

from serieux import Serieux
from serieux.exc import NotGivenError, ValidationError
from serieux.features.interpol import Environment, Interpolation
from serieux.features.partial import Sources
from tests.definitions import Country

deserialize = (Serieux + Interpolation)().deserialize

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
    assert deserialize(Player, data, Environment()) == Player(
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
    assert deserialize(Team, data, Environment()) == Team(
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
    players = deserialize(list[Player], data, Environment())
    assert str(players[1].nickname) == "Hos"
    assert str(players[2].nickname) == "Hoss"
    assert str(players[3].nickname) == "Hosss"


def test_refer_to_object():
    data = [{"name": "Jon", "nickname": "Pork", "number": 1}, "${0}"]
    players = deserialize(list[Player], data, Environment())
    assert players[0] == players[1]


@dataclass
class DateMix:
    sdate: str
    ddate: date


def test_further_conversion():
    data = {"sdate": "2025-05-01", "ddate": "${sdate}"}
    dm = deserialize(DateMix, data, Environment())
    assert dm.ddate == date(2025, 5, 1)


def test_further_conversion_2():
    data = {"sdate": "2025-05", "ddate": "${sdate}-01"}
    dm = deserialize(DateMix, data, Environment())
    assert dm.ddate == date(2025, 5, 1)


def test_deadlock():
    data = {"name": "${nickname}", "nickname": "${name}", "number": 1}
    player = deserialize(Player, data, Environment())
    with pytest.raises(Exception, match="Deadlock"):
        player.name == "x"


def test_env():
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TESTOTRON", "123")
        data = {"name": "Jon", "nickname": "Jonathan", "number": "${env:TESTOTRON}"}
        player = deserialize(Player, data, Environment())
        assert player.name == "Jon"
        assert player.number == 123


def test_env_types():
    vars = Environment(environ={"BOOL": "yes"})
    vars = Environment(
        environ={
            "BOOL": "yes",
            "INT": "42",
            "FLOAT": "3.14",
            "STR": "hello",
            "LIST": "a,b,c",
            "BOOL_FALSE": "no",
            "DICT": '{"a": 1, "b": 2}',
            "EMPTY": "",
            "NULL": "null",
            "NONE": "NONE",
        }
    )

    assert deserialize(bool, "${env:BOOL}", vars) is True
    assert deserialize(int, "${env:INT}", vars) == 42
    assert deserialize(int | None, "${env:INT}", vars) == 42
    assert deserialize(int | None, "${env:EMPTY}", vars) is None
    assert deserialize(float, "${env:FLOAT}", vars) == 3.14
    assert deserialize(str, "${env:STR}", vars) == "hello"
    assert deserialize(list[str], "${env:LIST}", vars) == ["a", "b", "c"]
    assert deserialize(bool, "${env:BOOL_FALSE}", vars) is False
    assert deserialize(bool, "${env:EMPTY}", vars) is False
    assert deserialize(NoneType, "${env:EMPTY}", vars) is None
    assert deserialize(NoneType, "${env:NULL}", vars) is None
    assert deserialize(NoneType, "${env:NONE}", vars) is None
    assert deserialize(dict[str, int], "${env:DICT}", vars) == {"a": 1, "b": 2}


def test_env_custom_deser():
    from .test_usermeth import RGB

    vars = Environment(environ={"COLOR": "#ff00ff"})
    rgb = deserialize(RGB, "${env:COLOR}", vars)
    assert rgb == RGB(red=255, green=0, blue=255)


def test_invalid_boolean():
    with pytest.raises(ValidationError, match="Cannot convert 'invalid' to boolean"):
        deserialize(bool, "${env:INVALID}", Environment(environ={"INVALID": "invalid"}))


def test_invalid_null():
    with pytest.raises(ValidationError, match="Cannot convert 'invalid' to None"):
        deserialize(NoneType, "${env:INVALID}", Environment(environ={"INVALID": "invalid"}))


def test_invalid_union():
    with pytest.raises(ValidationError, match="Cannot convert 'invalid' to boolean"):
        deserialize(int | bool, "${env:INVALID}", Environment(environ={"INVALID": "invalid"}))


def test_unsupported_resolver():
    with pytest.raises(
        ValidationError,
        match="Cannot resolve 'unknown:xyz' because the 'unknown' resolver is not defined",
    ):
        deserialize(str, "${unknown:xyz}", Environment())


def test_not_given():
    with pytest.raises(NotGivenError, match="Environment variable 'MISSING' is not defined"):
        deserialize(str, "${env:MISSING}", Environment())


@dataclass
class Fool:
    name: str
    iq: int = 100


def test_not_given_ignore():
    srcs = Sources({"name": "John"}, {"iq": "${env:INTEL}"})

    d = deserialize(Fool, srcs, Environment())
    assert d.iq == 100

    d = deserialize(Fool, srcs, Environment(environ={"INTEL": "31"}))
    assert d.iq == 31


_canada = str(datapath / "canada.yaml")
_france = str(datapath / "france.yaml")


@mock.patch.dict(os.environ, {"FILOU": _canada})
def test_resolve_envfile():
    canada = deserialize(Country, "${envfile:FILOU}", Environment())
    assert canada.capital == "Ottawa"


@mock.patch.dict(os.environ, {"FILOU": f"{_canada}, {_france}"})
def test_resolve_envfile_two_files():
    canada = deserialize(Country, "${envfile:FILOU}", Environment())
    assert canada.capital == "Ottawa"
    assert [c.name for c in canada.citizens] == ["Olivier", "Abraham", "Jeannot"]


def test_resolve_envfile_not_given():
    canada = deserialize(Country, Sources(Path(_canada), "${envfile:FILOU}"), Environment())
    assert canada.capital == "Ottawa"
