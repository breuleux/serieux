import pytest

from serieux import deserialize, schema, serialize
from serieux.exc import ValidationError
from serieux.features.registered import Registered, StringMapped, singleton


class Numero(StringMapped):
    one = 1
    two = 2
    three = 3


NumeroDeux = StringMapped.create("NumeroDeux", {"one": 1, "two": 2, "three": 3})


class Person(Registered):
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


def test_string_mapped_deserialize():
    assert deserialize(Numero, "one") == 1


def test_string_mapped_deserialize2():
    assert deserialize(NumeroDeux, "one") == 1


def test_string_mapped_deserialize_unknown():
    with pytest.raises(ValidationError, match="'bone' is not a registered option"):
        deserialize(Numero, "bone")


def test_string_mapped_serialize():
    assert serialize(Numero, 1) == "one"


def test_string_mapped_serialize_unknown():
    with pytest.raises(ValidationError, match="The value '33' is not registered"):
        serialize(Numero, 33)


def test_string_mapped_schema():
    sch = schema(Numero).compile(root=False)

    assert sch == {"type": "string", "enum": ["one", "two", "three"]}


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


class Tool(Registered):
    pass


@singleton("hammer")
class Hammer(Tool):
    def use(self):
        return "bang!"


@singleton
class Saw(Tool):
    def use(self):
        return "zing!"


def test_singleton():
    assert deserialize(Tool, "hammer") is Hammer
    assert deserialize(Tool, "saw") is Saw


def test_illegal_singleton():
    with pytest.raises(
        TypeError, match="must be a subclass of Registered, but not a direct subclass"
    ):

        @singleton
        class Bloop(Registered):
            pass
