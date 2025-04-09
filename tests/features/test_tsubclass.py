from dataclasses import dataclass

import pytest

from serieux import Serieux
from serieux.exc import ValidationError
from serieux.features.tsubclass import TaggedSubclass, TaggedSubclassFeature

featured = (Serieux + TaggedSubclassFeature)()
serialize = featured.serialize
deserialize = featured.deserialize


@dataclass
class Animal:
    name: str


@dataclass
class Cat(Animal):
    selfishness: int

    def cry(self):
        return "me" * self.selfishness + "ow"


@dataclass
class Wolf(Animal):
    size: int

    def cry(self):
        "a-woo" + "o" * self.size


def test_tagged_subclass():
    orig = Wolf(name="Wolfie", size=10)
    ser = serialize(TaggedSubclass[Animal], orig)
    assert ser == {
        "class": "tests.features.test_tsubclass:Wolf",
        "name": "Wolfie",
        "size": 10,
    }
    deser = deserialize(TaggedSubclass[Animal], ser)
    assert deser == orig


def test_serialize_not_top_level():
    class Lynx(Cat):
        pass

    orig = Lynx(name="Lina", selfishness=9)
    with pytest.raises(ValidationError, match="Only top-level symbols"):
        serialize(TaggedSubclass[Lynx], orig)


def test_serialize_wrong_class():
    orig = Wolf(name="Wolfie", size=10)
    with pytest.raises(ValidationError, match="Wolf.*is not a subclass of.*Cat"):
        serialize(TaggedSubclass[Cat], orig)


def test_deserialize_wrong_class():
    orig = {"class": "tests.features.test_tsubclass:Wolf", "name": "Wolfie", "size": 10}
    with pytest.raises(ValidationError, match="Wolf.*is not a subclass of.*Cat"):
        deserialize(TaggedSubclass[Cat], orig)


def test_resolve_default():
    ser = {"name": "Kevin"}
    assert deserialize(TaggedSubclass[Animal], ser) == Animal(name="Kevin")


def test_resolve_same_file():
    ser = {"class": "Cat", "name": "Katniss", "selfishness": 3}
    assert deserialize(TaggedSubclass[Animal], ser) == Cat(name="Katniss", selfishness=3)


def test_not_found():
    with pytest.raises(ValidationError, match="no attribute 'Bloop'"):
        ser = {"class": "Bloop", "name": "Quack"}
        deserialize(TaggedSubclass[Animal], ser)


def test_bad_resolve():
    with pytest.raises(ValidationError, match="Bad format for class reference"):
        ser = {"class": "x:y:z", "name": "Quack"}
        deserialize(TaggedSubclass[Animal], ser)
