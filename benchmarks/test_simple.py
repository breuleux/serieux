import json
from dataclasses import dataclass

import pytest
from apischema import serialize

from .interfaces import (
    apischema,
    marshmallow,
    mashumaro,
    old_serieux,
    pydantic,
    serieux,
)


@dataclass
class Citizen:
    name: str
    birthyear: int
    hometown: str


@dataclass
class Country:
    languages: list[str]
    capital: str
    population: int
    citizens: list[Citizen]


@dataclass
class World:
    countries: dict[str, Country]


canada = Country(
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


world = World(countries={"canada": canada})


roboland = Country(
    languages=[f"Robolang{i}" for i in range(10000)],
    capital="Robopolis",
    population=1000,
    citizens=[
        Citizen(
            f"Bobot{i}",
            birthyear=3000 + i,
            hometown=f"Bobotown{i}",
        )
        for i in range(1000)
    ],
)


@pytest.mark.benchmark(group="serialize_simple")
@pytest.mark.parametrize(
    "interface",
    [serieux, old_serieux, apischema, pydantic, marshmallow, mashumaro],
)
def test_serialize(interface, benchmark):
    fn = interface.serializer_for_type(World)
    result = benchmark(fn, world)
    assert result == serialize(World, world)


@pytest.mark.benchmark(group="json_simple")
@pytest.mark.parametrize(
    "interface",
    [serieux, old_serieux, apischema, pydantic, marshmallow, mashumaro],
)
def test_json(interface, benchmark):
    fn = interface.json_for_type(World)
    result = benchmark(fn, world)
    assert json.loads(result) == serialize(World, world)


@pytest.mark.benchmark(group="serialize_roboland")
@pytest.mark.parametrize(
    "interface",
    [serieux, old_serieux, apischema, pydantic, marshmallow, mashumaro],
)
def test_serialize_roboland(interface, benchmark):
    fn = interface.serializer_for_type(Country)
    result = benchmark(fn, roboland)
    assert result == serialize(Country, roboland)
