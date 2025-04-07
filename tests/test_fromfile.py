from pathlib import Path

import pytest

from serieux.ctx import AccessPath
from serieux.exc import ValidationError
from serieux.fromfile import FromFileFeature
from serieux.impl import BaseImplementation
from serieux.partial import Sources

from .common import Citizen, Country, World

deserialize = (BaseImplementation + FromFileFeature)().deserialize

here = Path(__file__).parent


def test_deserialize_from_file():
    assert deserialize(Country, here / "data" / "canada.yaml") == Country(
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
        here / "data" / "canada.yaml",
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
    world = deserialize(World, here / "data" / "world.yaml")
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


def test_deserialize_incomplete():
    with pytest.raises(ValidationError, match="KeyError: 'capital'"):
        deserialize(Country, here / "data" / "france.yaml", AccessPath())


def test_deserialize_invalid():
    with pytest.raises(ValidationError, match="Cannot deserialize object"):
        deserialize(Country, here / "data" / "invalid.yaml", AccessPath())
