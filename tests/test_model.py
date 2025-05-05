from dataclasses import dataclass
from numbers import Number
from typing import Literal

from serieux.model import field_at, model

from .common import has_312_features
from .definitions import Job, Pig, Point, Tree, Worker


def test_model_cached():
    ptm1 = model(Point)
    ptm2 = model(Point)
    assert ptm1 is ptm2


def test_model_recursive():
    tm = model(Tree)
    fleft = tm.fields[0]
    assert fleft.name == "left"
    assert fleft.type == Tree | Number


@has_312_features
def test_model_recursive_parametric():
    from .definitions_py312 import Tree

    tm = model(Tree[int])
    fleft = tm.fields[0]
    assert fleft.name == "left"
    assert fleft.type == Tree[int] | int


def test_model_default():
    assert model(int) is None


def test_model_none_default():
    m = model(Worker)
    assert len(m.fields) == 2
    assert m.fields[0].name == "name"
    assert m.fields[0].type is str
    assert m.fields[1].name == "job"
    assert m.fields[1].type == Job | None


@dataclass
class ColorBox:
    color: Literal["red", "green", "blue"]
    intensity: int = 100


def test_model_literal():
    m = model(ColorBox)
    assert len(m.fields) == 2
    assert m.fields[0].name == "color"
    assert m.fields[0].type == Literal["red", "green", "blue"]
    assert m.fields[1].name == "intensity"
    assert m.fields[1].type is int


def test_field_descriptions():
    m = model(Pig)
    p, w, b = m.fields

    assert p.name == "pinkness"
    assert p.description == "How pink the pig is"

    assert w.name == "weight"
    assert w.description == "Weight of the pig, in kilograms"

    assert b.name == "beautiful"
    assert b.description == "Is the pig...\ntruly...\n...beautiful?"


def test_eval_annotations_cross_file():
    from .lilmod.base import Point
    from .lilmod.ext import DrawingLine

    mdl = model(DrawingLine)
    assert {f.name: f.type for f in mdl.fields} == {"p1": Point, "p2": Point, "thickness": int}


def test_field_at():
    fld1 = field_at(dict[str, Worker], ["Jonathan", "job"])
    assert fld1.type == Job | None

    fld2 = field_at(dict[str, Worker], ["Jonathan", "job", "title"])
    assert fld2.name == "title"
    assert fld2.type is str

    fld3 = field_at(dict[str, Worker], ["Jonathan", "job", "gluglu"])
    assert fld3 is None

    fld4 = field_at(object, ["Jonathan", "job", "gluglu"])
    assert fld4 is None
