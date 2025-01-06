from typing import get_args

from ovld import ovld, recurse, subclasscheck

from serieux.typetags import TaggedType, make_tag
from tests.common import one_test_per_assert

Apple = make_tag(name="Apple", priority=1)
Banana = make_tag(name="Banana", priority=2)
Carrot = make_tag(name="Carrot", priority=3)
Dog = make_tag(name="Dog", priority=4)


def test_typetag_idempotent():
    assert Apple[int] is Apple[int]


def test_typetag_commutative():
    assert Apple[Banana[int]] is Banana[Apple[int]]


@one_test_per_assert
def test_typetag_strip():
    assert Apple.strip(Apple[int]) is int
    assert Apple.strip(Apple[Banana[int]]) is Banana[int]
    assert Apple.strip(Banana[Apple[int]]) is Banana[int]
    assert Apple.strip(Banana[int]) is Banana[int]
    assert Apple.strip(int) is int


@one_test_per_assert
def test_typetags():
    assert subclasscheck(Apple[int], Apple)
    assert subclasscheck(Apple[Banana[int | str]], Apple)
    assert subclasscheck(Apple[Banana[int | str]], Banana)
    assert not subclasscheck(Apple[object], Apple[int])
    assert not subclasscheck(Apple[int], int)
    assert not subclasscheck(int, Apple[int])


@one_test_per_assert
def test_pushdown():
    assert Apple[int].pushdown() is int
    assert Apple[list[int]].pushdown() == list[Apple[int]]
    assert Apple[Banana[list[int]]].pushdown() == list[Apple[Banana[int]]]


@ovld
def pie(typ: type[TaggedType], xs):
    return recurse(typ.pushdown(), xs)


@ovld
def pie(typ: type[list[object]], xs):
    return [recurse(get_args(typ)[0], x) for x in xs]


@ovld
def pie(typ: type[Apple[int]], x):
    return x + 1


@ovld
def pie(typ: type[Banana[int]], x):
    return x * 2


@ovld
def pie(typ: type[Carrot[object]], xs):
    return "carrot"


@ovld
def pie(typ: type[int], x):
    return x


def test_with_ovld():
    assert pie(int, 3) == 3
    assert pie(Apple[int], 3) == 4
    assert pie(list[int], [1, 2, 3]) == [1, 2, 3]
    assert pie(Apple[list[int]], [1, 2, 3]) == [2, 3, 4]
    assert pie(Banana[int], 3) == 6

    assert pie(Apple[Banana[int]], 3) == 6
    assert pie(list[Apple[Banana[int]]], [1, 2, 3]) == [2, 4, 6]
    assert pie(Apple[Banana[list[int]]], [1, 2, 3]) == [2, 4, 6]

    assert pie(Carrot[list[int]], [1, 2, 3]) == "carrot"
