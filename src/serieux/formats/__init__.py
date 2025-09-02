import importlib.metadata
from pathlib import Path

from .abc import FileFormat
from .unavailable import Unavailable

registry = {}


def register(suffix: str, ff: type[FileFormat]):
    registry[suffix] = ff()


def register_entry_points():
    for ep in importlib.metadata.entry_points(group="serieux.formats"):
        try:
            ff_cls = ep.load()
            register(ep.name, ff_cls)
        except ModuleNotFoundError as exc:  # pragma: no cover
            register(ep.name, Unavailable(ep.name, exc.name))


register_entry_points()


def find(p: Path, suffix: str | None = None):
    if suffix is None:
        suffix = p.suffix
    suffix = suffix.lstrip(".")
    return registry[suffix]


def load(p: Path, suffix: str | None = None):
    return find(p, suffix).load(p)


def dump(p: Path, data: object, suffix: str | None = None):
    return find(p, suffix).dump(p, data)
