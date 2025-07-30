from dataclasses import dataclass

import pytest

from serieux import Serieux, deserialize
from serieux.auto import Auto
from serieux.ctx import Context
from serieux.exc import ValidationError
from serieux.features.tagset import (
    Tag,
    Tagged,
    TaggedUnion,
    TagSet,
    TagSetFeature,
    tag_field,
    value_field,
)

from ..definitions import Player, Point

tu_serieux = (Serieux + TagSetFeature)()

deserialize = tu_serieux.deserialize
serialize = tu_serieux.serialize


def test_tagged_serialize():
    data = {tag_field: "point", "x": 1, "y": 2}
    assert serialize(Tagged[Point, "point"], Point(1, 2)) == data


def test_tagged_serialize_primitive():
    data = {tag_field: "nombre", value_field: 7}
    assert serialize(Tagged[int, "nombre"], 7) == data


def test_tagged_deserialize():
    data = {tag_field: "point", "x": 1, "y": 2}
    assert deserialize(Tagged[Point, "point"], data) == Point(1, 2)


def test_tagged_deserialize_primitive():
    data = {tag_field: "nombre", value_field: 7}
    assert deserialize(Tagged[int, "nombre"], data) == 7


def test_tunion_serialize():
    U = Tagged[Player, "player"] | Tagged[Point, "point"]
    data = {tag_field: "point", "x": 1, "y": 2}
    assert serialize(U, Point(1, 2), Context()) == data


def test_tunion_deserialize():
    U = Tagged[Player, "player"] | Tagged[Point, "point"]
    data = {tag_field: "point", "x": 1, "y": 2}
    assert deserialize(U, data) == Point(1, 2)


def test_tagged_default_tag():
    def f():
        pass

    assert TagSet.extract(Tagged[Point]).tag == "point"
    assert TagSet.extract(Tagged[Auto[f]]).tag == "f"


def test_tagged_union():
    us = [
        TaggedUnion[{"player": Player, "point": Point}],
        TaggedUnion[Player, Point],
        TaggedUnion[Point],
    ]
    for U in us:
        pt = Point(1, 2)
        data_point = {tag_field: "point", "x": 1, "y": 2}
        assert serialize(U, pt, Context()) == data_point
        assert deserialize(U, data_point) == pt

    for U in us[:-1]:
        ply = Player("Alice", "Smith", 0.333)
        data_player = {tag_field: "player", "first": "Alice", "last": "Smith", "batting": 0.333}
        assert serialize(U, ply, Context()) == data_player
        assert deserialize(U, data_player) == ply


@dataclass
class Blonde:
    name: str
    age: int


@dataclass
class Redhead:
    name: str
    age: int


def test_tagged_union_identical_fields():
    U = TaggedUnion[Blonde, Redhead]

    blonde = Blonde("Sam", 25)
    redhead = Redhead("Jack", 50)

    data_blonde = {tag_field: "blonde", "name": "Sam", "age": 25}
    data_redhead = {tag_field: "redhead", "name": "Jack", "age": 50}

    assert serialize(U, blonde, Context()) == data_blonde
    assert serialize(U, redhead, Context()) == data_redhead

    assert deserialize(U, data_blonde) == blonde
    assert deserialize(U, data_redhead) == redhead


def test_tag_validationerrors():
    lt = Tag("foo", Blonde)

    with pytest.raises(ValidationError, match="Tag 'foo' is required"):
        lt.get_type(None, ctx=None)

    with pytest.raises(ValidationError, match="Tag 'bar' does not match expected tag 'foo'"):
        lt.get_type("bar", ctx=None)

    with pytest.raises(
        ValidationError, match="Type '.*' does not match expected class '.*Blonde.*'"
    ):
        lt.get_tag(Redhead, ctx=None)
