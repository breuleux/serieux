from dataclasses import dataclass
from typing import Annotated

import pytest

from serieux import Serieux
from serieux.exc import ValidationError
from serieux.features.comment import Comment, CommentedObjects, CommentRec, comment_field
from serieux.features.proxy import CommentProxy
from serieux.features.tagset import value_field

featured = (Serieux + CommentedObjects)()
serialize = featured.serialize
deserialize = featured.deserialize


@dataclass
class Person:
    name: str
    age: int


def test_comment_serialize_int():
    proxy = CommentProxy(42, "The answer")
    serialized = serialize(Comment[int, str], proxy)
    expected = {value_field: 42, comment_field: "The answer"}
    assert serialized == expected


def test_comment_deserialize_int():
    serialized = {value_field: 42, comment_field: "The answer"}
    deserialized = deserialize(Comment[int, str], serialized)
    assert isinstance(deserialized, CommentProxy)
    assert deserialized._obj == 42
    assert deserialized._ == "The answer"


def test_comment_serialize_person():
    person = Person(name="Alice", age=30)
    proxy = CommentProxy(person, "A nice person")
    serialized = serialize(Comment[Person, str], proxy)
    expected = {"name": "Alice", "age": 30, comment_field: "A nice person"}
    assert serialized == expected


def test_comment_deserialize_person():
    serialized = {"name": "Alice", "age": 30, comment_field: "A nice person"}
    deserialized = deserialize(Comment[Person, str], serialized)
    assert isinstance(deserialized, CommentProxy)
    assert isinstance(deserialized._obj, Person)
    assert deserialized._obj == Person(name="Alice", age=30)
    assert deserialized._ == "A nice person"


def test_comment_with_complex_comment_type():
    comment_person = Person("Bob", 25)
    proxy = CommentProxy(100, comment_person)

    serialized = serialize(Comment[int, Person], proxy)
    expected = {value_field: 100, comment_field: {"name": "Bob", "age": 25}}
    assert serialized == expected

    deserialized = deserialize(Comment[int, Person], serialized)
    assert isinstance(deserialized, CommentProxy)
    assert deserialized._obj == 100
    assert deserialized._ == comment_person


def test_comment_without_comment_field():
    data = {"name": "Charlie", "age": 35}
    result = deserialize(Comment[Person, str], data)
    assert type(result) is Person
    assert result.name == "Charlie"
    assert result.age == 35


def test_comment_required_not_commentproxy():
    person = Person("Eve", 28)
    with pytest.raises(ValidationError):
        serialize(Annotated[Person, Comment(str, True)], person)


def test_comment_required_without_comment():
    data = {"name": "Charlie", "age": 35}
    with pytest.raises(ValidationError):
        deserialize(Annotated[Person, Comment(str, True)], data)


def test_comment_required_without_comment_int():
    data = 100
    with pytest.raises(ValidationError):
        deserialize(Annotated[int, Comment(str, True)], data)


def test_comment_serialize_non_proxy():
    person = Person("David", 40)
    serialized = serialize(Comment[Person, str], person)
    expected = {"name": "David", "age": 40}
    assert serialized == expected


def test_comment_serialize_proxy_to_normal_type():
    person = Person("David", CommentProxy(40, "v. young"))
    serialized = serialize(Person, person)
    expected = {"name": "David", "age": 40}
    assert serialized == expected


def test_comment_schema(schematest):
    schematest(
        type=Comment[Person, str],
        value=CommentProxy(Person("Alice", 30), "note"),
    )


def test_comment_schema_required(schematest):
    schematest(
        type=Annotated[Person, Comment(str, required=True)],
        value=CommentProxy(Person("Bob", 25), "required comment"),
    )


def test_comment_schema_primitive(schematest):
    schematest(
        type=Annotated[str, Comment(str, required=True)],
        value=CommentProxy("hello", "world"),
    )


def test_commentrec_serialize():
    person = Person("David", CommentProxy(40, "v. young"))

    serialized = serialize(CommentRec[Person, str], person)
    expected = {"name": "David", "age": {value_field: 40, comment_field: "v. young"}}
    assert serialized == expected

    deserialized = deserialize(CommentRec[Person, str], expected)
    assert deserialized == person
    assert deserialized.age._ == "v. young"
