import pytest

from serieux.proxy import Accessor, TrackingProxy

from .common import Point, one_test_per_assert


@pytest.fixture
def tp():
    yield TrackingProxy.make({"a": 1, "b": [2, 3], "c": Point(4, 5)})


@one_test_per_assert
def test_tracked(tp):
    assert str(tp["a"][Accessor]) == ".a"
    assert str(tp.get("a")[Accessor]) == ".a"
    assert str(tp.get("z", 3)[Accessor]) == ".z"
    assert str(tp["b"][1][Accessor]) == ".b[1]"
    assert str(tp["c"].x[Accessor]) == ".c.x"


def test_tracked_items(tp):
    for k, v in tp.items():
        assert str(v[Accessor]) == f".{k}"


def test_tracked_enumerate(tp):
    for i, x in enumerate(tp["b"]):
        assert str(x[Accessor]) == f".b[{i}]"
