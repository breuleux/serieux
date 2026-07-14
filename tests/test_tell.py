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


class Celsius:
    @classmethod
    def serieux_from_number(cls, obj):  # pragma: no cover
        return cls()

    @classmethod
    def serieux_to_number(cls, obj):  # pragma: no cover
        return 0


def test_tells_number_modelizable():
    assert tells(Celsius, int) == set()
    assert tells(Celsius, float) == set()
    assert tells(Celsius, str) is None
