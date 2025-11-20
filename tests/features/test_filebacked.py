from dataclasses import dataclass

import pytest

from serieux import Serieux
from serieux.features.filebacked import FileBacked, FileBackedFeature
from serieux.tell import tells

from ..definitions import Point

srx = (Serieux + FileBackedFeature)()


@dataclass
class Config:
    point: Point @ FileBacked(proxy=True, default_factory=lambda: Point(0, 0))


@dataclass
class ConfigNoProxy:
    point: Point @ FileBacked(default_factory=lambda: Point(5, 10))


@dataclass
class ConfigNoDefault:
    point: Point @ FileBacked(proxy=True)


def test_filebacked_proxy_basic(tmp_path):
    point_file = tmp_path / "point.yaml"

    srx.dump(Point, Point(1, 2), dest=point_file)

    config = srx.deserialize(Config, {"point": str(point_file)})

    assert config.point.x == 1
    assert config.point.y == 2
    assert config.point._path == point_file

    config.point.x = 10
    config.point.y = 20

    config.point.save()

    reloaded = srx.deserialize(Point, point_file)
    assert reloaded.x == 10
    assert reloaded.y == 20


def test_filebacked_proxy_default_factory(tmp_path):
    point_file = tmp_path / "nonexistent.yaml"

    config = srx.deserialize(Config, {"point": str(point_file)})

    assert config.point.x == 0
    assert config.point.y == 0

    config.point.x = 3
    config.point.y = 7
    config.point.save()

    assert point_file.exists()
    reloaded = srx.deserialize(Point, point_file)
    assert reloaded.x == 3
    assert reloaded.y == 7


def test_filebacked_no_proxy(tmp_path):
    """Test FileBacked without proxy."""
    point_file = tmp_path / "point.yaml"

    srx.dump(Point, Point(2, 3), dest=point_file)

    config = srx.deserialize(ConfigNoProxy, {"point": str(point_file)})

    assert config.point.value.x == 2
    assert config.point.value.y == 3
    assert config.point.path == point_file

    config.point.value.x = 15
    config.point.value.y = 25

    config.point.save()

    reloaded = srx.deserialize(Point, point_file)
    assert reloaded.x == 15
    assert reloaded.y == 25


def test_filebacked_no_proxy_default_factory(tmp_path):
    point_file = tmp_path / "new_point.yaml"

    config = srx.deserialize(ConfigNoProxy, {"point": str(point_file)})

    assert config.point.value.x == 5
    assert config.point.value.y == 10

    config.point.save()

    assert point_file.exists()
    reloaded = srx.deserialize(Point, point_file)
    assert reloaded.x == 5
    assert reloaded.y == 10


def test_filebacked_no_default_raises(tmp_path):
    point_file = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError):
        srx.deserialize(ConfigNoDefault, {"point": str(point_file)})


def test_filebacked_reload(tmp_path):
    point_file = tmp_path / "point.yaml"

    srx.dump(Point, Point(1, 1), dest=point_file)

    config = srx.deserialize(Config, {"point": str(point_file)})
    assert config.point.x == 1
    assert config.point.y == 1

    srx.dump(Point, Point(99, 99), dest=point_file)

    config.point.load()

    assert config.point.x == 99
    assert config.point.y == 99


def test_filebacked_serialize(tmp_path):
    point_file = tmp_path / "point.yaml"
    srx.dump(Point, Point(4, 5), dest=point_file)
    config = srx.deserialize(Config, {"point": str(point_file)})
    serialized = srx.serialize(Config, config)
    assert serialized == {"point": str(point_file)}


def test_filebacked_serialize_no_proxy(tmp_path):
    point_file = tmp_path / "point.yaml"
    srx.dump(Point, Point(8, 9), dest=point_file)
    config = srx.deserialize(ConfigNoProxy, {"point": str(point_file)})
    serialized = srx.serialize(ConfigNoProxy, config)
    assert serialized == {"point": str(point_file)}


def test_filebacked_str_repr(tmp_path):
    point_file = tmp_path / "point.yaml"

    srx.dump(Point, Point(7, 8), dest=point_file)

    config = srx.deserialize(Config, {"point": str(point_file)})
    str_repr = str(config.point)
    assert "Point(x=7, y=8)" in str_repr
    assert str(point_file) in str_repr

    config_no_proxy = srx.deserialize(ConfigNoProxy, {"point": str(point_file)})
    str_repr = str(config_no_proxy.point)
    assert "Point(x=7, y=8)" in str_repr
    assert str(point_file) in str_repr


def test_filebacked_schema():
    schema = srx.schema(Config).compile(root=False)
    assert schema == {
        "type": "object",
        "properties": {"point": {"type": "string"}},
        "required": ["point"],
        "additionalProperties": False,
    }


def test_filebacked_tells():
    assert tells(expected=Point @ FileBacked(), given=str) == set()
