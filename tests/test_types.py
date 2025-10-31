import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from serieux import JSON, deserialize, serialize
from serieux.ctx import WorkingDirectory
from serieux.exc import ValidationError
from serieux.tell import tells

from .test_schema import schema

# Tests for non-principal types


#############
# Test date #
#############


def test_serialize_date():
    assert serialize(date, date(2023, 5, 15)) == "2023-05-15"
    assert serialize(list[date], [date(2023, 5, 15), date(2024, 1, 1)]) == [
        "2023-05-15",
        "2024-01-01",
    ]


def test_serialize_date_error():
    with pytest.raises(ValidationError, match="Cannot serialize"):
        serialize(date, "2023-05-15")
    with pytest.raises(ValidationError, match="Cannot serialize"):
        serialize(list[date], ["2023-05-15", "2024-01-01"])


def test_deserialize_date():
    assert deserialize(date, "2023-05-15") == date(2023, 5, 15)
    assert deserialize(list[date], ["2023-05-15", "2024-01-01"]) == [
        date(2023, 5, 15),
        date(2024, 1, 1),
    ]


def test_schema_date():
    assert schema(date) == {"type": "string", "format": "date"}


def test_tells_date():
    assert tells(date, str) == set()


#################
# Test datetime #
#################


def test_serialize_datetime():
    assert serialize(datetime, datetime(2023, 5, 15, 12, 30, 45)) == "2023-05-15T12:30:45"
    assert serialize(
        list[datetime], [datetime(2023, 5, 15, 12, 30, 45), datetime(2024, 1, 1, 0, 0, 0)]
    ) == ["2023-05-15T12:30:45", "2024-01-01T00:00:00"]


def test_deserialize_datetime():
    assert deserialize(datetime, "2023-05-15T12:30:45") == datetime(2023, 5, 15, 12, 30, 45)
    assert deserialize(list[datetime], ["2023-05-15T12:30:45", "2024-01-01T00:00:00"]) == [
        datetime(2023, 5, 15, 12, 30, 45),
        datetime(2024, 1, 1, 0, 0, 0),
    ]


def test_deserialize_datetime_timestamp():
    assert deserialize(datetime, 1746471553) == datetime.fromtimestamp(1746471553)


def test_schema_datetime():
    assert schema(datetime) == {"type": "string", "format": "date-time"}


def test_tells_datetime():
    assert tells(datetime, str) == set()


##################
# Test timedelta #
##################


def test_serialize_timedelta():
    assert serialize(timedelta, timedelta(seconds=42)) == "42s"
    assert serialize(timedelta, timedelta(seconds=42, microseconds=500000)) == "42500000us"
    assert serialize(timedelta, timedelta(seconds=-10)) == "-10s"
    assert serialize(list[timedelta], [timedelta(seconds=30), timedelta(days=5)]) == [
        "30s",
        "432000s",
    ]


def test_deserialize_timedelta():
    assert deserialize(timedelta, "42s") == timedelta(seconds=42)
    assert deserialize(timedelta, "42500000us") == timedelta(seconds=42, microseconds=500000)
    assert deserialize(timedelta, "-10s") == timedelta(seconds=-10)
    assert deserialize(timedelta, "6h30m") == timedelta(hours=6, minutes=30)
    assert deserialize(timedelta, "+8d") == timedelta(days=8)
    assert deserialize(timedelta, "4.5d") == timedelta(days=4, seconds=60 * 60 * 12)
    assert deserialize(timedelta, "1d12h") == timedelta(days=1, hours=12)
    assert deserialize(timedelta, "36h") == timedelta(days=1, hours=12)
    assert deserialize(list[timedelta], ["30s", "5d"]) == [
        timedelta(seconds=30),
        timedelta(days=5),
    ]
    with pytest.raises(ValidationError, match="is not a valid timedelta"):
        deserialize(timedelta, "1dd")
    with pytest.raises(ValidationError, match="is not a valid timedelta"):
        deserialize(timedelta, "1d3")
    with pytest.raises(ValidationError, match="is not a valid timedelta"):
        deserialize(timedelta, "1d3x")
    with pytest.raises(ValidationError, match="Could not convert"):
        deserialize(timedelta, "1.5.4d")


def test_schema_timedelta():
    assert schema(timedelta) == {
        "type": "string",
        "pattern": r"^[+-]?([\d.]+[dhms]|[\d.]+ms|[\d.]+us)+$",
    }


def test_tells_timedelta():
    assert tells(timedelta, str) == set()


#############
# Test Path #
#############


def test_serialize_path():
    assert serialize(Path, Path("hello/world.txt")) == "hello/world.txt"
    assert (
        serialize(Path, Path("hello/world.txt"), WorkingDirectory(directory=Path("hello")))
        == "world.txt"
    )


def test_deserialize_path():
    assert deserialize(Path, "hello/world.txt") == Path("hello/world.txt")
    assert deserialize(Path, "world.txt", WorkingDirectory(directory=Path("hello"))) == Path(
        "hello/world.txt"
    )


def test_schema_path():
    assert schema(Path) == {"type": "string"}


def test_tells_path():
    assert tells(Path, str) == set()


#################
# Test ZoneInfo #
#################


def test_serialize_zoneinfo():
    assert serialize(ZoneInfo, ZoneInfo("America/New_York")) == "America/New_York"
    assert serialize(ZoneInfo, ZoneInfo("UTC")) == "UTC"


def test_deserialize_zoneinfo():
    assert deserialize(ZoneInfo, "America/New_York") == ZoneInfo("America/New_York")
    assert deserialize(ZoneInfo, "UTC") == ZoneInfo("UTC")
    with pytest.raises(ZoneInfoNotFoundError, match="No time zone found"):
        deserialize(ZoneInfo, "Invalid/Timezone")


def test_schema_zoneinfo():
    assert schema(ZoneInfo) == {"type": "string"}


def test_tells_zoneinfo():
    assert tells(ZoneInfo, str) == set()


###################
# Test re.Pattern #
###################


def test_serialize_pattern():
    pattern = re.compile(r"\d+")
    assert serialize(re.Pattern, pattern) == r"\d+"

    pattern_with_flags = re.compile(r"hello", re.IGNORECASE)
    assert serialize(re.Pattern, pattern_with_flags) == "hello"


def test_deserialize_pattern():
    pattern = deserialize(re.Pattern, r"\d+")
    assert isinstance(pattern, re.Pattern)
    assert pattern.pattern == r"\d+"
    assert pattern.match("123") is not None
    assert pattern.match("abc") is None


def test_deserialize_complex_pattern():
    complex_pattern = deserialize(re.Pattern, r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    assert complex_pattern.pattern == r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    assert complex_pattern.match("test@example.com") is not None
    assert complex_pattern.match("invalid-email") is None


def test_deserialize_pattern_invalid():
    with pytest.raises(Exception, match="bad character range"):
        deserialize(re.Pattern, r"[z-a]")  # Invalid character range


def test_serialize_deserialize_dict_pattern_str():
    pattern1 = re.compile(r"\d+")
    pattern2 = re.compile(r"hello")
    d = {pattern1: "numbers", pattern2: "greeting"}

    serialized = serialize(dict[re.Pattern, str], d)
    assert serialized == {r"\d+": "numbers", "hello": "greeting"}

    deserialized = deserialize(
        dict[re.Pattern, str],
        {r"\d+": "numbers", "hello": "greeting"},
    )
    assert deserialized == d


def test_schema_pattern():
    assert schema(re.Pattern) == {"type": "string"}


def test_tells_pattern():
    assert tells(re.Pattern, str) == set()


#############
# Test JSON #
#############


class NotJson:
    pass


def test_serialize_json():
    data = {"a": 1, "b": [2, 3], "c": {"d": "hello"}}
    assert serialize(JSON, data) == data
    assert serialize(list[JSON], [data, 42, "foo"]) == [data, 42, "foo"]
    with pytest.raises(ValidationError):
        serialize(JSON, NotJson())


def test_deserialize_json():
    data = {"a": 1, "b": [2, 3], "c": {"d": "hello"}}
    assert deserialize(JSON, data) == data
    assert deserialize(list[JSON], [data, 42, "foo"]) == [data, 42, "foo"]
    with pytest.raises(ValidationError):
        deserialize(JSON, NotJson())


def test_schema_json():
    assert schema(JSON) == {}
