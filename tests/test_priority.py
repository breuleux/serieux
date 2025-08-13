from itertools import pairwise

from serieux.priority import (
    DEFAULT,
    HI1,
    HI2,
    HI3,
    HI4,
    HI5,
    HI6,
    HI7,
    HI8,
    HI9,
    HIGH,
    LO1,
    LO2,
    LO3,
    LO4,
    LO5,
    LOW,
    MAX,
    MIN,
    STD,
    STD1,
    STD2,
    STD3,
    STD4,
    STD5,
    NamedInteger,
    PriorityLevel,
)


def test_ni_creation():
    ni = NamedInteger(42, "test")
    assert ni == 42
    assert int(ni) == 42
    assert ni._name == "test"
    assert isinstance(ni, int)


def test_ni_string_representation():
    ni = NamedInteger(100, "MAX")
    assert str(ni) == "MAX"
    assert repr(ni) == "MAX"


def test_ni_arithmetic_operations():
    ni = NamedInteger(10, "TEN")
    assert ni + 5 == 15
    assert ni - 3 == 7
    assert ni * 2 == 20
    assert ni // 2 == 5


def test_ni_comparison_operations():
    ni1 = NamedInteger(5, "FIVE")
    ni2 = NamedInteger(10, "TEN")
    assert ni1 < ni2
    assert ni2 > ni1


def test_pl_next_method():
    ni = NamedInteger(5, "FIVE")
    pl = PriorityLevel(ni)
    assert pl.next() == (5, 1)
    assert pl.next() == (5, 2)
    assert pl.next() == (5, 3)
    assert pl.next().next() == (5, 4, 1)


def test_call_method():
    ni = NamedInteger(5, "FIVE")
    pl = PriorityLevel(ni)
    assert pl(10, "extra") == (ni, 10, "extra")


def test_order():
    seq = [
        MAX,
        HI9,
        HI8,
        HI7,
        HI6,
        HI5,
        HI4,
        HI3,
        HI2,
        HI1,
        DEFAULT,
        STD5,
        STD4,
        STD3,
        STD2,
        STD1,
        LO1,
        LO2,
        LO3,
        LO4,
        LO5,
        MIN,
    ]
    assert all(a > b for a, b in pairwise(seq))


def test_aliases():
    assert DEFAULT == (0,)
    assert STD == STD1
    assert HIGH == HI1
    assert LOW == LO1
