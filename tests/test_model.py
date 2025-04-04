from dataclasses import dataclass
from numbers import Number

from serieux.model import model

from .common import Point
from .definitions import Tree


def test_model_cached():
    ptm1 = model(Point)
    ptm2 = model(Point)
    assert ptm1 is ptm2


def test_model_recursive():
    tm = model(Tree)
    fleft = tm.fields[0]
    assert fleft.name == "left"
    assert fleft.type == tm | Number


def test_model_recursive_parametric():
    from .definitions_py312 import Tree

    tm = model(Tree[int])
    fleft = tm.fields[0]
    assert fleft.name == "left"
    assert fleft.type == tm | int


def test_model_default():
    assert model(int) is int


def test_model_idempotent():
    assert model(model(int)) is model(int)


@dataclass
class Pig:
    # How pink the pig is
    pinkness: float

    weight: float
    """Weight of the pig, in kilograms"""

    # Is the pig...
    # truly...
    beautiful: bool = True  # ...beautiful?


def test_field_descriptions():
    m = model(Pig)
    p, w, b = m.fields

    assert p.name == "pinkness"
    assert p.description == "How pink the pig is"

    assert w.name == "weight"
    assert w.description == "Weight of the pig, in kilograms"

    assert b.name == "beautiful"
    assert b.description == "Is the pig...\ntruly...\n...beautiful?"
