import importlib.metadata
from dataclasses import dataclass
from pathlib import Path

from .abc import FileFormat


@dataclass
class FileSource:
    path: Path
    format: FileFormat = None
    field: str = None

    def __post_init__(self):
        if not isinstance(self.format, FileFormat):
            self.format = find(self.path, suffix=self.format)

    @classmethod
    def serieux_from_string(cls, incl):
        pth, at, fld = incl.partition("@")
        return cls(Path(pth.strip()), field=fld if at else None)


class FormatRegistry(dict):
    def __missing__(self, item):
        match importlib.metadata.entry_points(group="serieux.formats", name=item):
            case [ep, *__]:
                ff_cls = ep.load()
                ff = ff_cls()
                self[item] = ff
                return ff
            case _:
                raise ImportError(f"Format `{item}` is not recognized.")


registry = FormatRegistry()


def find(p: Path, suffix: str | None = None):
    if suffix is None:
        suffix = p.suffix
    suffix = suffix.lstrip(".")
    return registry[suffix]


def load(p: Path, suffix: str | None = None):
    return find(p, suffix).load(p)


def dump(p: Path, data: object, suffix: str | None = None):
    return find(p, suffix).dump(p, data)


def loads(s: str, suffix: str | None = None):
    return find(None, suffix).loads(s)


def dumps(data: object, suffix: str | None = None):
    return find(None, suffix).dumps(data)
