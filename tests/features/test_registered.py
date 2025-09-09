from typing import Any

import pytest

from serieux import deserialize, schema, serialize
from serieux.exc import ValidationError
from serieux.features.registered import AutoRegistered, Referenced, Registry, auto_singleton
from tests.definitions import Job

teacher = Job(title="Teacher", yearly_pay=50000)
engineer = Job(title="Engineer", yearly_pay=90000)
artist = Job(title="Artist", yearly_pay=40000)


def test_registry():
    reg = Registry(
        {
            "teacher": teacher,
            "artist": artist,
        }
    )
    assert deserialize(Job @ reg, "teacher") is teacher
    assert serialize(Job @ reg, artist) == "artist"

    with pytest.raises(ValidationError):
        deserialize(Job @ reg, "engineer")

    with pytest.raises(ValidationError):
        serialize(Job @ reg, engineer)


def test_referenced():
    assert deserialize(Referenced[Job], "tests.features.test_registered:teacher") is teacher
    with pytest.raises(ValidationError):
        assert serialize(Referenced[Job], teacher)


def test_referenced_function():
    sym = "tests.features.test_registered:test_referenced_function"
    assert deserialize(Referenced[Any], sym) is test_referenced_function
    assert serialize(Referenced[Any], test_referenced_function) == sym


class Person(AutoRegistered):
    def __init__(self, name, age):
        super().__init__(name)
        self.name = name
        self.age = age


class SuperPerson(Person):
    def __init__(self, name, age, power):
        super().__init__(name, age)
        self.power = power


anita = Person("anita", 76)
bernard = Person("bernard", 73)
charlotte = SuperPerson("charlotte", 33, "spits fire")


def test_registered_serialize():
    assert serialize(Person, anita) == "anita"
    assert serialize(Person, bernard) == "bernard"
    assert serialize(Person, charlotte) == "charlotte"


def test_registered_deserialize():
    assert deserialize(Person, "anita") is anita
    assert deserialize(Person, "bernard") is bernard
    assert deserialize(Person, "charlotte") is charlotte


def test_registered_schema():
    sch = schema(Person).compile(root=False)

    assert sch == {"type": "string", "enum": ["anita", "bernard", "charlotte"]}


class Tool(AutoRegistered):
    pass


@auto_singleton("HAMMER")
class Hammer(Tool):
    def use(self):
        return "bang!"


@auto_singleton
class Saw(Tool):
    def use(self):
        return "zing!"


def test_singleton_deserialize():
    assert deserialize(Tool, "HAMMER") is Hammer
    assert deserialize(Tool, "saw") is Saw
    with pytest.raises(ValidationError):
        deserialize(Tool, "nail")


def test_singleton_serialize():
    assert serialize(Tool, Hammer) == "HAMMER"
    assert serialize(Tool, Saw) == "saw"
    with pytest.raises(ValidationError):
        serialize(Tool, object())


def test_illegal_singleton():
    with pytest.raises(
        TypeError, match="must be a subclass of Registered, but not a direct subclass"
    ):

        @auto_singleton
        class Bloop(AutoRegistered):
            pass
