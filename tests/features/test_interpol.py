from dataclasses import dataclass
from datetime import date

import pytest

from serieux import Serieux
from serieux.features.interpol import VariableInterpolation, Variables

deserialize = (Serieux + VariableInterpolation)().deserialize


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
