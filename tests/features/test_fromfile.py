import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from serieux import Serieux
from serieux.ctx import AccessPath
from serieux.exc import ValidationError
from serieux.features.fromfile import FromFileFeature
from serieux.features.partial import Sources

from ..common import Citizen, Country, World

deserialize = (Serieux + FromFileFeature)().deserialize

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


@pytest.fixture
def check_error_display(capsys, file_regression):
    @contextmanager
    def check(message="", exc_type=ValidationError):
        with pytest.raises(exc_type, match=message) as exc:
            yield

        exc.value.display(file=sys.stderr)
        cap = capsys.readouterr()
        out = cap.out.replace(str(datapath.parent), "REDACTED")
        err = cap.err.replace(str(datapath.parent), "REDACTED")
        file_regression.check("\n".join([out, "=" * 80, err]))

    yield check


def test_deserialize_incomplete(check_error_display):
    with check_error_display("KeyError: 'capital'"):
        deserialize(Country, datapath / "france.yaml", AccessPath())


def test_deserialize_invalid(check_error_display):
    with check_error_display("Cannot deserialize object"):
        deserialize(Country, datapath / "invalid.yaml", AccessPath())


def test_deserialize_oops_world(check_error_display):
    with check_error_display("Cannot deserialize object"):
        deserialize(World, datapath / "oops-world.yaml", AccessPath())
