from serieux import Serieux, deserialize
from serieux.auto import Auto
from serieux.ctx import Context
from serieux.features.tagged import Tagged, TaggedTypes, TaggedUnion

from ..definitions import Player, Point

tu_serieux = (Serieux + TaggedTypes)()

deserialize = tu_serieux.deserialize
serialize = tu_serieux.serialize


def test_isinstance():
    assert isinstance(1, Tagged[int, "bob"])
    assert issubclass(int, Tagged[int, "bob"])


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

    assert Tagged[Point].tag == "point"
    assert Tagged[Auto[f]].tag == "f"


def test_tagged_union():
    us = [
        TaggedUnion[{"player": Player, "point": Point}],
        TaggedUnion[Player, Point],
        TaggedUnion[Point],
    ]
    for U in us:
        data = {"class": "point", "x": 1, "y": 2}
        assert serialize(U, Point(1, 2), Context()) == data
        assert deserialize(U, data) == Point(1, 2)
