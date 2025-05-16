from __future__ import annotations

import itertools
import json
from dataclasses import dataclass

import pytest
from apischema import serialize

from .interfaces import (
    apischema,
    marshmallow,
    mashumaro,
    pydantic,
    serde,
    serieux,
)


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Tree:
    left: Tree | int
    right: Tree | int


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


point = Point(x=17, y=83)


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


tree = Tree(1, Tree(Tree(2, 3), Tree(4, Tree(5, Tree(6, Tree(7, Tree(8, 9)))))))


id_to_thing = {id(v): k for k, v in globals().items()}


def bench(interfaces, data):
    cases = list(itertools.product(data, interfaces))
    return pytest.mark.parametrize(
        "data,interface",
        cases,
        ids=[f"{id_to_thing[id(d)]},{id_to_thing[id(i)]}" for d, i in cases],
    )


@bench(
    interfaces=[
        apischema,
        pydantic,
        serde,
        marshmallow,
        mashumaro,
        serieux,
    ],
    data=[point, world, roboland, tree],
)
def test_serialize(interface, data, benchmark):
    fn = interface.serializer_for_type(type(data))
    result = benchmark(fn, data)
    assert result == serialize(type(data), data)


@bench(
    interfaces=[
        apischema,
        pydantic,
        serde,
        marshmallow,
        mashumaro,
        serieux,
    ],
    data=[roboland],
)
def test_json(interface, data, benchmark):
    fn = interface.json_for_type(type(data))
    result = benchmark(fn, data)
    assert json.loads(result) == serialize(type(data), data)


@bench(
    interfaces=[
        marshmallow,
        apischema,
        pydantic,
        serde,
        mashumaro,
        serieux,
    ],
    data=[point, world, roboland, tree],
)
def test_deserialize(interface, data, benchmark):
    data_ser = serialize(data)
    fn = interface.deserializer_for_type(type(data))
    result = benchmark(fn, data_ser)
    assert result == data
