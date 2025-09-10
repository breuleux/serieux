from ..utils import import_any
from .abc import FileFormat

loads = import_any(
    feature="TOML loading",
    candidates={
        "toml": lambda m: m.loads,
        "tomllib": lambda m: m.loads,
        "tomli": lambda m: m.loads,
        "tomli_w": None,
    },
)

dumps = import_any(
    feature="TOML dumping",
    candidates={
        "toml": lambda m: m.dumps,
        "tomli-w:tomli_w": lambda m: m.dumps,
        "tomli": None,
        "tomllib": None,
    },
)


class TOML(FileFormat):
    def loads(self, s: str):
        return loads(s)

    def dumps(self, data):
        return dumps(data)
