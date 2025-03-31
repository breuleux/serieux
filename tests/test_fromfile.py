from pathlib import Path

from serieux.fromfile import FromFileFeature
from serieux.impl import BaseImplementation
from serieux.partial import Sources

from .common import Citizen, Country

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
