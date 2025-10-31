from serieux.tell import tells


def test_tells_int():
    assert tells(int, int) == set()
    assert tells(int, str) is None


def test_tells_float():
    assert tells(float, float) == set()
    assert tells(float, str) is None


def test_tells_bool():
    assert tells(bool, bool) == set()
    assert tells(bool, dict) is None
