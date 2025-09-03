import importlib.metadata
from pathlib import Path


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
