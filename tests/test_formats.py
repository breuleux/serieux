import pytest

from serieux.formats import dump, dumps, load, loads

data = {
    "plums": 38,
    "hello": "world",
    "things": [1, 2, 3.5, True],
}

cases = [
    ("json", data),
    ("pkl", data),
    ("yaml", data),
    ("toml", data),
    ("txt", "hello!"),
]


@pytest.mark.parametrize("suffix, value", cases)
def test_dump_and_load(tmp_path, suffix, value):
    file = tmp_path / f"test.{suffix}"
    dump(file, value, suffix)
    loaded = load(file, suffix)
    assert loaded == value


str_cases = [
    ("json", data),
    ("yaml", data),
    ("toml", data),
    ("txt", "hello!"),
]


@pytest.mark.parametrize("suffix, value", str_cases)
def test_dumps_and_loads(suffix, value):
    dumped = dumps(value, suffix)
    loaded = loads(dumped, suffix)
    assert loaded == value
