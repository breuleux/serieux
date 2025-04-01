from dataclasses import dataclass

import pytest

from serieux.impl import BaseImplementation
from serieux.tsubclass import TaggedSubclass, TaggedSubclassFeature

featured = (BaseImplementation + TaggedSubclassFeature)()
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
        "class": "tests.test_tsubclass:Wolf",
        "name": "Wolfie",
        "size": 10,
    }
    deser = deserialize(TaggedSubclass[Animal], ser)
    assert deser == orig


def test_wrong_class():
    orig = Wolf(name="Wolfie", size=10)
    with pytest.raises(TypeError, match="Wolf.*is not a subclass of.*Cat"):
        serialize(TaggedSubclass[Cat], orig)


def test_resolve_default():
    ser = {"name": "Kevin"}
    assert deserialize(TaggedSubclass[Animal], ser) == Animal(name="Kevin")


def test_resolve_same_file():
    ser = {"class": "Cat", "name": "Katniss", "selfishness": 3}
    assert deserialize(TaggedSubclass[Animal], ser) == Cat(name="Katniss", selfishness=3)


def test_not_found():
    with pytest.raises(Exception, match="no attribute 'Bloop'"):
        ser = {"class": "Bloop", "name": "Quack"}
        deserialize(TaggedSubclass[Animal], ser)


def test_bad_resolve():
    with pytest.raises(Exception, match="Bad format for class reference"):
        ser = {"class": "x:y:z", "name": "Quack"}
        deserialize(TaggedSubclass[Animal], ser)
