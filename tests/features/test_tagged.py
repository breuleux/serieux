from dataclasses import dataclass

from serieux import Serieux, deserialize
from serieux.auto import Auto
from serieux.ctx import Context
from serieux.features.tagset import Tagged, TaggedUnion, TagSet, TagSetFeature

from ..definitions import Player, Point

tu_serieux = (Serieux + TagSetFeature)()

deserialize = tu_serieux.deserialize
serialize = tu_serieux.serialize


def test_tagged_serialize():
    data = {"class": "point", "x": 1, "y": 2}
    assert serialize(Tagged[Point, "point"], Point(1, 2)) == data


def test_tagged_serialize_primitive():
    data = {"class": "nombre", "return": 7}
    assert serialize(Tagged[int, "nombre"], 7) == data


def test_tagged_deserialize():
    data = {"class": "point", "x": 1, "y": 2}
    assert deserialize(Tagged[Point, "point"], data) == Point(1, 2)


def test_tagged_deserialize_primitive():
    data = {"class": "nombre", "return": 7}
    assert deserialize(Tagged[int, "nombre"], data) == 7


def test_tunion_serialize():
    U = Tagged[Player, "player"] | Tagged[Point, "point"]
    data = {"class": "point", "x": 1, "y": 2}
    assert serialize(U, Point(1, 2), Context()) == data


def test_tunion_deserialize():
    U = Tagged[Player, "player"] | Tagged[Point, "point"]
    data = {"class": "point", "x": 1, "y": 2}
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
        data_point = {"class": "point", "x": 1, "y": 2}
        assert serialize(U, pt, Context()) == data_point
        assert deserialize(U, data_point) == pt

    for U in us[:-1]:
        ply = Player("Alice", "Smith", 0.333)
        data_player = {"class": "player", "first": "Alice", "last": "Smith", "batting": 0.333}
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

    data_blonde = {"class": "blonde", "name": "Sam", "age": 25}
    data_redhead = {"class": "redhead", "name": "Jack", "age": 50}

    assert serialize(U, blonde, Context()) == data_blonde
    assert serialize(U, redhead, Context()) == data_redhead

    assert deserialize(U, data_blonde) == blonde
    assert deserialize(U, data_redhead) == redhead
