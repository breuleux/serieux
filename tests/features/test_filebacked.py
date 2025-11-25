from dataclasses import dataclass

import pytest

from serieux import Serieux
from serieux.features.filebacked import (
    DefaultFactory,
    FileBacked,
    FileBackedFeature,
    FileProxy,
)
from serieux.tell import tells

from ..definitions import Point

srx = (Serieux + FileBackedFeature)()


@dataclass
class Config:
    point: Point @ FileProxy(default_factory=lambda: Point(0, 0))


@dataclass
class ConfigNoDefault:
    point: Point @ FileProxy()


def test_filebacked_deserialize(tmp_path):
    point_file = tmp_path / "point.yaml"

    srx.dump(Point, Point(2, 3), dest=point_file)

    pf = srx.deserialize(FileBacked[Point], str(point_file))

    assert pf.value.x == 2
    assert pf.value.y == 3
    assert pf.path == point_file

    pf.value.x = 15
    pf.value.y = 25

    pf.save()

    reloaded = srx.deserialize(Point, point_file)
    assert reloaded.x == 15
    assert reloaded.y == 25


def test_filebacked_serialize(tmp_path):
    point_file = tmp_path / "point.yaml"
    srx.dump(Point, Point(8, 9), dest=point_file)
    config = srx.deserialize(FileBacked[Point], str(point_file))
    serialized = srx.serialize(FileBacked[Point], config)
    assert serialized == str(point_file)


def test_filebacked_default_factory(tmp_path):
    point_file = tmp_path / "nonexistent.yaml"

    pf = srx.deserialize(FileBacked[Point @ DefaultFactory(lambda: Point(5, 10))], str(point_file))

    assert pf.value.x == 5
    assert pf.value.y == 10

    pf.value.x = 3
    pf.value.y = 7
    pf.save()

    assert point_file.exists()
    reloaded = srx.deserialize(Point, point_file)
    assert reloaded.x == 3
    assert reloaded.y == 7


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


def test_fileproxy_no_default_raises(tmp_path):
    point_file = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError):
        srx.deserialize(ConfigNoDefault, {"point": str(point_file)})


def test_fileproxy_reload(tmp_path):
    point_file = tmp_path / "point.yaml"

    srx.dump(Point, Point(1, 1), dest=point_file)

    config = srx.deserialize(Config, {"point": str(point_file)})
    assert config.point.x == 1
    assert config.point.y == 1

    srx.dump(Point, Point(99, 99), dest=point_file)

    config.point.load()

    assert config.point.x == 99
    assert config.point.y == 99


def test_fileproxy_serialize(tmp_path):
    point_file = tmp_path / "point.yaml"
    srx.dump(Point, Point(4, 5), dest=point_file)
    config = srx.deserialize(Config, {"point": str(point_file)})
    serialized = srx.serialize(Config, config)
    assert serialized == {"point": str(point_file)}


def test_filebacked_str_repr(tmp_path):
    point_file = tmp_path / "point.yaml"

    srx.dump(Point, Point(7, 8), dest=point_file)

    pf = srx.deserialize(FileBacked[Point], str(point_file))
    str_repr = str(pf)
    assert str_repr == repr(pf)
    assert "Point(x=7, y=8)@" in str_repr
    assert str(point_file) in str_repr


def test_fileproxy_str_repr(tmp_path):
    point_file = tmp_path / "point.yaml"

    srx.dump(Point, Point(7, 8), dest=point_file)

    pf = srx.deserialize(Point @ FileProxy, str(point_file))
    str_repr = str(pf)
    assert str_repr == repr(pf)
    assert "Point(x=7, y=8)@" in str_repr
    assert str(point_file) in str_repr


def test_fileproxy_tells():
    assert tells(expected=Point @ FileProxy(), given=str) == set()


def test_filebacked_tells():
    assert tells(expected=FileBacked[Point], given=str) == set()


def test_filebacked_schema():
    schema = srx.schema(FileBacked[Point]).compile(root=False)
    assert schema == {"type": "string"}


def test_fileproxy_schema():
    schema = srx.schema(Point @ FileProxy).compile(root=False)
    assert schema == {"type": "string"}
