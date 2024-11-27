from dataclasses import dataclass
import json

from apischema import serialize

from .interfaces import apischema, marshmallow, pydantic, serieux, mashumaro
import pytest


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


world = World(
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
                )
            ]
        )
    }
)


@pytest.mark.benchmark(group="serialize_simple")
@pytest.mark.parametrize("interface", [serieux, apischema, pydantic, marshmallow, mashumaro])
def test_serialize(interface, benchmark):
    fn = interface.serializer_for_type(World)
    result = benchmark(fn, world)
    assert result == serialize(World, world)


@pytest.mark.benchmark(group="json_simple")
@pytest.mark.parametrize("interface", [serieux, apischema, pydantic, marshmallow, mashumaro])
def test_json(interface, benchmark):
    fn = interface.json_for_type(World)
    result = benchmark(fn, world)
    assert json.loads(result) == serialize(World, world)
