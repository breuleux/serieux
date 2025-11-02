import json
import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import NoneType

import pytest

from serieux import Serieux
from serieux.ctx import Sourced, Trail, WorkingDirectory
from serieux.exc import ValidationError
from serieux.features.fromfile import IncludeFile, include_field
from serieux.features.partial import Sources
from serieux.model import Field, Model

from ..definitions import Character, Citizen, Country, Elf, Job, Player, Team, Worker, World

deserialize = (Serieux + IncludeFile)().deserialize

here = Path(__file__).parent


def test_deserialize_from_file(datapath):
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


def test_deserialize_override(datapath):
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


def test_deserialize_world(datapath):
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


def test_deserialize_world_clone(datapath):
    world = deserialize(World, datapath / "clone.yaml")
    assert world == World(
        countries={
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


def test_deserialize_json(datapath):
    file = datapath / "world.json"
    # Sanity check that this is a valid JSON file
    json.loads(file.read_text())
    world = deserialize(World, file)
    world_baseline = deserialize(World, file.with_suffix(".yaml"))
    assert world == world_baseline


def test_deserialize_toml(datapath):
    file = datapath / "world.toml"
    # Sanity check that this is a valid TOML file
    tomllib.loads(file.read_text())
    world = deserialize(World, file)
    world_baseline = deserialize(World, file.with_suffix(".yaml"))
    assert world == world_baseline


def test_deserialize_missing_file(datapath):
    with pytest.raises(ValidationError, match="does not exist"):
        deserialize(World, datapath / "missing.yaml")


def test_deserialize_read_direct(
    datapath,
):
    team = deserialize(Team, datapath / "team.yaml")
    assert team.players[0] == Player(first="Olivier", last="Breuleux", batting=0.9)


def test_deserialize_incomplete(datapath, check_error_display):
    with check_error_display("Missing required field 'capital'"):
        deserialize(Country, datapath / "france.yaml", Trail())


def test_deserialize_invalid(datapath, check_error_display):
    with check_error_display("Cannot deserialize string"):
        deserialize(Country, datapath / "invalid.yaml", Trail())


def test_deserialize_invalid_indirect(datapath, check_error_display):
    with check_error_display("Some errors occurred"):
        deserialize(World, datapath / "world-invalid.yaml", Trail())


def test_deserialize_oops_world(datapath, check_error_display):
    with check_error_display("Cannot deserialize string"):
        deserialize(World, datapath / "oops-world.yaml", Trail())


def test_deserialize_oops_elves(datapath, check_error_display):
    with check_error_display("Invalid isoformat string", exc_type=ValueError):
        deserialize(dict[str, Elf], datapath / "elves.yaml")


def test_deserialize_oops_elves_ap(datapath, check_error_display):
    with check_error_display("Invalid isoformat string", exc_type=ValueError):
        deserialize(dict[str, Elf], datapath / "elves.yaml", Trail())


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
    wd = Sourced(origin=origin)
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


def test_deserialize_types(datapath):
    data = deserialize(Datatypes, datapath / "all.yaml")
    assert data == Datatypes(
        strong="hello", integger=5, flowhat=4.4, boule=True, nuttin=None, date=date(2025, 1, 3)
    )


def test_deserialize_default_from_file(datapath):
    data = deserialize(Worker, datapath / "worker-include.yaml")
    assert data == Worker(name="Humbert", job=Job(title="Lawyer", yearly_pay=1000000.0))


def test_include_txt(datapath):
    data = deserialize(Character, datapath / "character.yaml")
    assert data == Character(
        name="Jimbo Mayo",
        age=32,
        occupation="Journalist",
        backstory=(datapath / "jimbo.txt").read_text(),
    )


def test_include_format(datapath):
    construct = {
        include_field: {"path": str(datapath / "character.yaml"), "format": "txt"},
    }
    data = deserialize(str, construct)
    assert data == (datapath / "character.yaml").read_text()


def test_bad_format(datapath):
    construct = {
        include_field: {"path": str(datapath / "character.yaml"), "format": "unknown"},
    }
    with pytest.raises(ImportError, match=r"Format `unknown` is not recognized"):
        deserialize(str, construct)


def test_include_list(datapath):
    construct = {
        include_field: [
            {"path": str(datapath / "france.yaml")},
            {"path": str(datapath / "france-capital.yaml")},
        ]
    }
    data = deserialize(Country, construct)
    assert data == Country(
        languages=["French"],
        population=13,
        citizens=[
            Citizen(name="Jeannot", birthyear=1893, hometown="Lyon"),
        ],
        capital="Paris",
    )


def test_include_list_for_list_type(datapath):
    construct = {
        include_field: [
            {"path": str(datapath / "things.yaml")},
            {"path": str(datapath / "thangs.yaml")},
        ]
    }
    data = deserialize(set[str], construct)
    assert data == {
        "Pants",
        "Jackets",
        "Yo-yos",
        "Pajamas",
        "Maggots",
        "French kisses",
    }


@dataclass
class Loves:
    loves: list[str]

    def say(self):
        return f"I love {', '.join(self.loves)}"
        # INSERT_YOUR_CODE

    @classmethod
    def serieux_model(cls, call_next):
        return Model(
            original_type=cls,
            element_field=Field(name="*", type=str),
            list_constructor=lambda xs: Loves(list(xs)),
        )


def test_include_loves(datapath):
    construct = {
        include_field: [
            {"path": str(datapath / "things.yaml")},
            {"path": str(datapath / "thangs.yaml")},
        ]
    }
    lv = deserialize(Loves, construct)
    assert lv.say() == "I love Pants, Jackets, Yo-yos, Pajamas, Maggots, French kisses"
