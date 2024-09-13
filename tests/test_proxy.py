from serieux.proxy import Accessor, TrackingProxy
from tests.common import Point


def test_tracked():
    tp = TrackingProxy.make({"a": 1, "b": [2, 3], "c": Point(4, 5)})

    assert str(tp["a"][Accessor]) == "['a']"
    assert str(tp.get("a")[Accessor]) == "['a']"
    assert str(tp.get("z", 3)[Accessor]) == "['z']"
    assert str(tp["b"][1][Accessor]) == "['b'][1]"
    assert str(tp["c"].x[Accessor]) == "['c'].x"

    for k, v in tp.items():
        assert str(v[Accessor]) == f"['{k}']"

    for i, x in enumerate(tp["b"]):
        assert str(x[Accessor]) == f"['b'][{i}]"
