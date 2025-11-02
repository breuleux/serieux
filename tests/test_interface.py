from datetime import date

import pytest
from ovld import Medley

from serieux import deserializer, get_deserializer, get_serializer, schema_definition, serializer
from serieux.ctx import Context
from serieux.exc import ValidationError
from tests.definitions import Point


class Beep:
    def __init__(self, value: int):
        self.value = value

    def __eq__(self, other):
        return self.value == other.value


def test_custom_serializer(fresh_serieux):
    with pytest.raises(ValidationError):
        fresh_serieux.serialize(Beep, Beep(7))

    @serializer
    def _s(self, t: type[Beep], obj: Beep, ctx: Context):
        return obj.value

    @serializer(priority=-1)
    def _s(self, t: type[Beep], obj: Beep, ctx: Context):
        assert False, "should not use this method"

    assert fresh_serieux.serialize(Beep, Beep(7)) == 7


def test_custom_deserializer(fresh_serieux):
    with pytest.raises(ValidationError):
        fresh_serieux.deserialize(Beep, 7)

    @deserializer
    def _d(self, t: type[Beep], obj: int, ctx: Context):
        return Beep(obj)

    @deserializer(priority=-1)
    def _d(self, t: type[Beep], obj: int, ctx: Context):
        assert False, "should not use this method"

    assert fresh_serieux.deserialize(list[Beep], [1, 2, 3]) == [Beep(1), Beep(2), Beep(3)]


def test_custom_schema(fresh_serieux):
    @schema_definition
    def _sch(self, t: type[Beep], ctx: Context):
        return {"type": "integer"}

    @schema_definition(priority=-1)
    def _sch(self, t: type[Beep], ctx: Context):
        assert False, "should not use this method"

    assert fresh_serieux.schema(Beep).compile(root=False) == {"type": "integer"}


class Kustom(Medley):
    def deserialize(self, t: type[Beep], obj: str, ctx: Context):
        return Beep(int(obj))


def test_inherits(fresh_serieux):
    srx = fresh_serieux + Kustom()

    with pytest.raises(ValidationError):
        srx.deserialize(Beep, 7)
    assert srx.deserialize(Beep, "9") == Beep(9)

    @deserializer
    def _d(self, t: type[Beep], obj: int, ctx: Context):
        return Beep(obj)

    assert srx.deserialize(Beep, 7) == Beep(7)
    assert srx.deserialize(Beep, "9") == Beep(9)


def test_serializer_for():
    assert get_serializer(Point)(Point(1, 2)) == {"x": 1, "y": 2}
    assert get_serializer(list[Point])([Point(1, 2)]) == [{"x": 1, "y": 2}]


def test_deserializer_for():
    assert get_deserializer(Point)({"x": 1, "y": 2}) == Point(1, 2)
    assert get_deserializer(list[Point])([{"x": 1, "y": 2}]) == [Point(1, 2)]
    assert get_deserializer(int)(42) == 42
    assert get_deserializer(date)("2025-12-01") == date(2025, 12, 1)
