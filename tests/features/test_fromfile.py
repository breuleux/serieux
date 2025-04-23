import json
import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import NoneType

import pytest

from serieux import Serieux
from serieux.ctx import AccessPath
from serieux.exc import ValidationError
from serieux.features.fromfile import FromFileExtra, WorkingDirectory
from serieux.features.partial import Sources

from ..definitions import Citizen, Country, Player, Team, World

deserialize = (Serieux + FromFileExtra)().deserialize

here = Path(__file__).parent
datapath = Path(__file__).parent.parent / "data"


def test_deserialize_from_file():
    assert deserialize(Country, datapath / "canada.yaml") == Country(
        languages=["English", "French"],
        capital="Ottawa",
        population=39_000_000,
        citizens=[
            Citizen(
                name="Olivier",
                birthyear=1985,
                hometown="Montreal",
            ),
            Citizen(
                name="Abraham",
                birthyear=2018,
                hometown="Shawinigan",
            ),
        ],
    )


def test_deserialize_override():
    srcs = Sources(
        datapath / "canada.yaml",
        {"capital": "Montreal"},
    )
    assert deserialize(Country, srcs) == Country(
        languages=["English", "French"],
        capital="Montreal",
        population=39_000_000,
        citizens=[
            Citizen(
                name="Olivier",
                birthyear=1985,
                hometown="Montreal",
            ),
            Citizen(
                name="Abraham",
                birthyear=2018,
                hometown="Shawinigan",
            ),
        ],
    )


def test_deserialize_world():
    world = deserialize(World, datapath / "world.yaml")
    assert world == World(
        countries={
            "canada": Country(
                languages=["English", "French"],
                capital="Ottawa",
                population=39_000_000,
                citizens=[
                    Citizen(
                        name="Olivier",
                        birthyear=1985,
                        hometown="Montreal",
                    ),
                    Citizen(
                        name="Abraham",
                        birthyear=2018,
                        hometown="Shawinigan",
                    ),
                ],
            ),
            "france": Country(
                languages=["French"],
                capital="Paris",
                population=68_000_000,
                citizens=[
                    Citizen(
                        name="Jeannot",
                        birthyear=1893,
                        hometown="Lyon",
                    ),
                ],
            ),
        }
    )


def test_deserialize_json():
    file = datapath / "world.json"
    # Sanity check that this is a valid JSON file
    json.loads(file.read_text())
    world = deserialize(World, file)
    world_baseline = deserialize(World, file.with_suffix(".yaml"))
    assert world == world_baseline


def test_deserialize_toml():
    file = datapath / "world.toml"
    # Sanity check that this is a valid TOML file
    tomllib.loads(file.read_text())
    world = deserialize(World, file)
    world_baseline = deserialize(World, file.with_suffix(".yaml"))
    assert world == world_baseline


def test_deserialize_missing_file():
    with pytest.raises(ValidationError, match="Could not read data"):
        deserialize(World, datapath / "missing.yaml")


def test_deserialize_read_direct():
    team = deserialize(Team, datapath / "team.yaml")
    assert team.players[0] == Player(first="Olivier", last="Breuleux", batting=0.9)


def test_deserialize_incomplete(check_error_display):
    with check_error_display("KeyError: 'capital'"):
        deserialize(Country, datapath / "france.yaml", AccessPath())


def test_deserialize_invalid(check_error_display):
    with check_error_display("Cannot deserialize string"):
        deserialize(Country, datapath / "invalid.yaml", AccessPath())


def test_deserialize_oops_world(check_error_display):
    with check_error_display("Cannot deserialize string"):
        deserialize(World, datapath / "oops-world.yaml", AccessPath())


def test_make_path_for(tmp_path):
    wd = WorkingDirectory(directory=tmp_path)
    path = wd.make_path_for(name="test_file", suffix=".txt")
    assert path.name == "test_file.txt"
    assert path.parent == tmp_path
    assert not path.exists()


def test_save(tmp_path):
    wd = WorkingDirectory(directory=tmp_path)
    txt = "Some delicious text"
    relpath = wd.save_to_file(txt, suffix=".txt")
    path = wd.directory / relpath
    assert path.exists()
    assert path.read_text() == txt


def test_save_bytes(tmp_path):
    wd = WorkingDirectory(directory=tmp_path)
    rbytes = os.urandom(100)
    relpath = wd.save_to_file(rbytes, suffix=".txt")
    path = wd.directory / relpath
    assert path.exists()
    assert path.read_bytes() == rbytes


def test_save_callback(tmp_path):
    li = []
    wd = WorkingDirectory(directory=tmp_path)
    relpath = wd.save_to_file(callback=li.append, suffix=".txt")
    path = wd.directory / relpath
    assert li == [path]


def test_wd_origin(tmp_path):
    origin = tmp_path / "xxx.yaml"
    wd = WorkingDirectory(origin=origin)
    assert wd.origin == origin
    assert wd.directory == tmp_path


@dataclass
class Datatypes:
    strong: str
    integger: int
    flowhat: float
    boule: bool
    nuttin: NoneType
    date: date | None


def test_deserialize_types():
    data = deserialize(Datatypes, datapath / "all.yaml")
    assert data == Datatypes(
        strong="hello", integger=5, flowhat=4.4, boule=True, nuttin=None, date=date(2025, 1, 3)
    )
