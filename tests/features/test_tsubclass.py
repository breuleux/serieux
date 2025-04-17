import json
from dataclasses import dataclass

import pytest

from serieux import Serieux, schema
from serieux.exc import ValidationError
from serieux.features.partial import Sources
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
class HouseCat(Cat):
    cute: bool = True


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
    @dataclass
    class Lynx:
        name: str
        selfishness: int

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


@dataclass
class Animals:
    alpha: TaggedSubclass[Animal]
    betas: list[TaggedSubclass[Animal]]


def test_tsubclass_partial():
    animals = deserialize(
        Animals,
        Sources(
            {
                "alpha": {
                    "class": "tests.features.test_tsubclass:Wolf",
                    "name": "Wolfie",
                    "size": 10,
                },
                "betas": [],
            },
        ),
    )
    assert isinstance(animals.alpha, Wolf)


def test_tsubclass_partial_merge():
    animals = deserialize(
        Animals,
        Sources(
            {
                "alpha": {
                    "class": "tests.features.test_tsubclass:Wolf",
                    "name": "Wolfie",
                    "size": 10,
                },
                "betas": [],
            },
            {"alpha": {"class": "tests.features.test_tsubclass:Wolf", "size": 13}},
        ),
    )
    assert isinstance(animals.alpha, Wolf)
    assert animals.alpha.name == "Wolfie"
    assert animals.alpha.size == 13


def test_tsubclass_partial_merge_subclass_left():
    animals = deserialize(
        Animals,
        Sources(
            {"alpha": {"name": "Roar"}},
            {
                "alpha": {
                    "class": "tests.features.test_tsubclass:Wolf",
                    "size": 10,
                },
                "betas": [],
            },
        ),
    )
    assert isinstance(animals.alpha, Wolf)
    assert animals.alpha.name == "Roar"
    assert animals.alpha.size == 10


def test_tsubclass_partial_merge_subclass_right():
    animals = deserialize(
        Animals,
        Sources(
            {
                "alpha": {
                    "class": "tests.features.test_tsubclass:Wolf",
                    "name": "Wolfie",
                    "size": 10,
                },
                "betas": [],
            },
            {"alpha": {"name": "Roar"}},
        ),
    )
    assert isinstance(animals.alpha, Wolf)
    assert animals.alpha.name == "Roar"
    assert animals.alpha.size == 10


def test_tsubclass_schema(file_regression):
    sch = schema(TaggedSubclass[Animal])
    file_regression.check(json.dumps(sch.compile(), indent=4))
