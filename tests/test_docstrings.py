from dataclasses import dataclass

from serieux.docstrings import get_attribute_docstrings, get_variable_data


@dataclass
class CommentedFields:
    # The name
    # of the person
    name: str
    # The age in years
    age: int
    # Whether the person is active
    is_active: bool = False
    # Optional email address
    email: str | None = None


@dataclass
class DocsFields:
    name: str
    """The person's full name."""

    age: int
    """The person's age in years."""

    is_active: bool = False
    """Whether the person's account is currently active."""

    email: str | None = None
    """The person's email address, if provided."""


def test_commented_fields():
    results = get_attribute_docstrings(CommentedFields)
    assert results == {
        "name": "The name\nof the person",
        "age": "The age in years",
        "is_active": "Whether the person is active",
        "email": "Optional email address",
    }


def test_docs_fields():
    results = get_attribute_docstrings(DocsFields)
    assert results == {
        "name": "The person's full name.",
        "age": "The person's age in years.",
        "is_active": "Whether the person's account is currently active.",
        "email": "The person's email address, if provided.",
    }


def add(
    # x coordinate
    x: int,
    # y coordinate
    y: int,
):
    return x + y


def test_function_docs():
    results = get_variable_data(add)
    assert results == {
        "x": "x coordinate",
        "y": "y coordinate",
    }


def add_pos(
    # xx coordinate
    xx: int,
    /,
    # yy coordinate
    yy: int,
):
    return xx + yy


def test_function_docs_2():
    results = get_variable_data(add_pos)
    assert results == {
        "xx": "xx coordinate",
        "yy": "yy coordinate",
    }
