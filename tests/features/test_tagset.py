import json
from dataclasses import dataclass
from typing import Annotated, Any

import pytest

from serieux import Serieux, schema
from serieux.exc import ValidationError
from serieux.features.dotted import DottedNotation
from serieux.features.partial import Sources
from serieux.features.tagset import (
    FromEntryPoint,
    ReferencedClass,
    TagDict,
    TaggedSubclass,
    TagSetFeature,
    tag_field,
)

from ..definitions import Point

featured = (Serieux + TagSetFeature)()
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


@pytest.fixture
def chalou():
    td = TagDict()
    td.register("chat", Cat)
    td.register("loup", Wolf)
    return td


def test_tagdict_get_type(chalou):
    assert chalou.get_type("chat") is Cat
    assert chalou.get_type("loup") is Wolf


def test_tagdict_get_type_invalid(chalou):
    with pytest.raises(ValidationError):
        chalou.get_type("dog")


def test_tagdict_get_tag(chalou):
    assert chalou.get_tag(Cat) == "chat"
    assert chalou.get_tag(Wolf) == "loup"


def test_tagdict_get_tag_invalid(chalou):
    with pytest.raises(ValidationError):
        chalou.get_tag(HouseCat)


def test_tagdict_iterate(chalou):
    items = set(chalou.iterate(Animal))
    assert items == {("chat", Cat), ("loup", Wolf)}


def test_tagdict_register():
    tagset1 = TagDict()
    tagset1.register("chat", Cat)
    tagset1.register("loup", Wolf)
    assert tagset1.possibilities == {"chat": Cat, "loup": Wolf}

    tagset2 = TagDict()
    tagset2.register("chat")(Cat)
    tagset2.register("loup")(Wolf)
    assert tagset2.possibilities == {"chat": Cat, "loup": Wolf}

    tagset3 = TagDict()
    tagset3.register(Cat)
    tagset3.register(Wolf)
    assert tagset3.possibilities == {"cat": Cat, "wolf": Wolf}


def test_tagdict_serialize(chalou):
    cat = Cat(name="Kitty", selfishness=3)
    ser = serialize(Annotated[Animal, chalou], cat)
    assert ser == {
        tag_field: "chat",
        "name": "Kitty",
        "selfishness": 3,
    }


def test_tagdict_deserialize(chalou):
    ser = {
        tag_field: "chat",
        "name": "Kitty",
        "selfishness": 3,
    }
    cat = Cat(name="Kitty", selfishness=3)
    deser = deserialize(Annotated[Animal, chalou], ser)
    assert deser == cat


def test_tagdict_ser_deser2(chalou):
    wolf = Wolf(name="Wolfie", size=5)
    ser_wolf = serialize(Annotated[Animal, chalou], wolf)
    assert ser_wolf == {
        tag_field: "loup",
        "name": "Wolfie",
        "size": 5,
    }
    deser_wolf = deserialize(Annotated[Animal, chalou], ser_wolf)
    assert deser_wolf == wolf


def test_tagdict_default():
    td = TagDict({"default": Cat, "loup": Wolf})
    cat = Cat(name="Kitty", selfishness=3)
    ser_cat = serialize(Annotated[Animal, td], cat)
    assert ser_cat == {
        "name": "Kitty",
        "selfishness": 3,
    }
    deser_cat = deserialize(Annotated[Animal, td], ser_cat)
    assert deser_cat == cat


def test_tagdict_schema(file_regression, chalou):
    sch = schema(Annotated[Animal, chalou])
    file_regression.check(json.dumps(sch.compile(), indent=4))


def test_merge_tagsets(file_regression):
    cha = TagDict({"chat": Cat})
    lou = TagDict({"loup": Wolf})

    cat = Cat(name="Kitty", selfishness=3)
    wolf = Wolf(name="Wolfie", size=5)

    ser_cat = serialize(Annotated[Animal, cha, lou], cat)
    assert ser_cat == {
        tag_field: "chat",
        "name": "Kitty",
        "selfishness": 3,
    }
    deser_cat = deserialize(Annotated[Animal, cha, lou], ser_cat)
    assert deser_cat == cat

    ser_wolf = serialize(Annotated[Animal, cha, lou], wolf)
    assert ser_wolf == {
        tag_field: "loup",
        "name": "Wolfie",
        "size": 5,
    }
    deser_wolf = deserialize(Annotated[Animal, cha, lou], ser_wolf)
    assert deser_wolf == wolf

    sch = schema(Annotated[Animal, cha, lou])
    file_regression.check(json.dumps(sch.compile(), indent=4))

    housecat = HouseCat(name="Mimi", selfishness=8)
    with pytest.raises(ValidationError, match="No tagset could resolve for type"):
        serialize(Annotated[Animal, cha, lou], housecat)

    with pytest.raises(ValidationError, match="No tagset could resolve the tag"):
        deserialize(
            Annotated[Animal, cha, lou],
            {
                tag_field: "housecat",
                "name": "Mimi",
                "selfishness": 8,
            },
        )


def test_tagged_subclass():
    orig = Wolf(name="Wolfie", size=10)
    ser = serialize(TaggedSubclass[Animal], orig)
    assert ser == {
        tag_field: "tests.features.test_tagset:Wolf",
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
    orig = {tag_field: "tests.features.test_tagset:Wolf", "name": "Wolfie", "size": 10}
    with pytest.raises(ValidationError, match="Wolf.*is not a subclass of.*Cat"):
        deserialize(TaggedSubclass[Cat], orig)


def test_resolve_default():
    ser = {"name": "Kevin"}
    assert deserialize(TaggedSubclass[Animal], ser) == Animal(name="Kevin")


def test_resolve_same_file():
    ser = {tag_field: "Cat", "name": "Katniss", "selfishness": 3}
    assert deserialize(TaggedSubclass[Animal], ser) == Cat(name="Katniss", selfishness=3)


def test_not_found():
    with pytest.raises(ValidationError, match="no attribute 'Bloop'"):
        ser = {tag_field: "Bloop", "name": "Quack"}
        deserialize(TaggedSubclass[Animal], ser)


def test_bad_resolve():
    with pytest.raises(ValidationError, match="Bad format for class reference"):
        ser = {tag_field: "x:y:z", "name": "Quack"}
        deserialize(TaggedSubclass[Animal], ser)


@dataclass
class Animals:
    alpha: TaggedSubclass[Animal]
    betas: list[TaggedSubclass[Animal]]


def test_tagged_subclass_partial():
    animals = deserialize(
        Animals,
        Sources(
            {
                "alpha": {
                    tag_field: "tests.features.test_tagset:Wolf",
                    "name": "Wolfie",
                    "size": 10,
                },
                "betas": [],
            },
        ),
    )
    assert isinstance(animals.alpha, Wolf)


def test_tagged_subclass_partial_merge():
    animals = deserialize(
        Animals,
        Sources(
            {
                "alpha": {
                    tag_field: "tests.features.test_tagset:Wolf",
                    "name": "Wolfie",
                    "size": 10,
                },
                "betas": [],
            },
            {"alpha": {tag_field: "tests.features.test_tagset:Wolf", "size": 13}},
        ),
    )
    assert isinstance(animals.alpha, Wolf)
    assert animals.alpha.name == "Wolfie"
    assert animals.alpha.size == 13


def test_tagged_subclass_partial_merge_subclass_left():
    animals = deserialize(
        Animals,
        Sources(
            {"alpha": {"name": "Roar"}},
            {
                "alpha": {
                    tag_field: "tests.features.test_tagset:Wolf",
                    "size": 10,
                },
                "betas": [],
            },
        ),
    )
    assert isinstance(animals.alpha, Wolf)
    assert animals.alpha.name == "Roar"
    assert animals.alpha.size == 10


def test_tagged_subclass_partial_merge_subclass_right():
    animals = deserialize(
        Animals,
        Sources(
            {
                "alpha": {
                    tag_field: "tests.features.test_tagset:Wolf",
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


def test_tagged_subclass_schema(file_regression):
    sch = schema(TaggedSubclass[Animal])
    file_regression.check(json.dumps(sch.compile(), indent=4))


def test_tagged_subclass_schema_fully_qualified(file_regression):
    sch = schema(Annotated[Animal, ReferencedClass])
    file_regression.check(json.dumps(sch.compile(), indent=4))


def test_open_schema():
    sch = schema(Annotated[Any, ReferencedClass])
    assert sch.compile(root=False) == {"type": "object", "additionalProperties": True}


def test_from_entry_points():
    # NOTE: serieux needs to be properly installed, e.g. with pip install or uv sync,
    # for the entry points to be registered
    OptF = Annotated[Any, FromEntryPoint("serieux.optional_features")]
    ser = serialize(OptF, DottedNotation())
    assert ser == {tag_field: "dotted"}
    assert deserialize(OptF, ser) == DottedNotation()
    sch = schema(OptF).compile(root=False)
    possibilities = {x["properties"][tag_field]["const"] for x in sch["oneOf"]}
    assert "dotted" in possibilities
    assert "autotag" in possibilities
    assert "include_file" in possibilities


def test_from_entry_points_with_default():
    # NOTE: serieux needs to be properly installed, e.g. with pip install or uv sync,
    # for the entry points to be registered
    OptF = Annotated[Any, FromEntryPoint("serieux.optional_features", default=DottedNotation)]
    ser = serialize(OptF, DottedNotation())
    assert ser == {}
    assert deserialize(OptF, {}) == DottedNotation()
    assert deserialize(OptF, {tag_field: "dotted"}) == DottedNotation()
    sch = schema(OptF).compile(root=False)
    assert any(
        ((tag_field not in x.get("properties", {})) or x.get("required") == [])
        for x in sch["oneOf"]
    )
    possibilities = {
        x["properties"][tag_field]["const"]
        for x in sch["oneOf"]
        if tag_field in x.get("properties", {})
    }
    assert "dotted" in possibilities
    assert "autotag" in possibilities
    assert "include_file" in possibilities


def test_from_entry_points_with_wrap():
    # NOTE: serieux needs to be properly installed, e.g. with pip install or uv sync,
    # for the entry points to be registered

    sub = {DottedNotation: Point}

    def wrap(x):
        return sub.get(x, x)

    OptF = Annotated[Any, FromEntryPoint("serieux.optional_features", wrap=wrap)]
    deser = deserialize(OptF, {tag_field: "dotted", "x": 1, "y": 2})
    assert deser == Point(1, 2)


def test_from_entry_points_errors():
    # NOTE: serieux needs to be properly installed, e.g. with pip install or uv sync,
    # for the entry points to be registered

    OptF = Annotated[Any, FromEntryPoint("serieux.optional_features")]

    with pytest.raises(ValidationError, match="No tag provided for entry point lookup"):
        deserialize(OptF, {})

    with pytest.raises(ValidationError, match="is not registered in entry point group"):
        deserialize(OptF, {tag_field: "not_a_real_entry_point"})

    fe = FromEntryPoint("serieux.optional_features")

    class NotRegistered:
        pass

    with pytest.raises(ValidationError, match="No entry point tag is registered for type"):
        fe.get_tag(NotRegistered, ctx=None)
