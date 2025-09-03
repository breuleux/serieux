from functools import partial
from pathlib import Path

from ..utils import import_any
from .abc import FileFormat

loads, dumps = import_any(
    feature="JSON loading and dumping",
    candidates={
        "msgspec.json": lambda m: (m.decode, m.encode),
        "orjson": lambda m: (m.loads, m.dumps),
        "ujson": lambda m: (m.loads, partial(m.dumps, ensure_ascii=False)),
        "json": lambda m: (m.loads, partial(m.dumps, ensure_ascii=False)),
    },
)


class JSON(FileFormat):
    def load(self, f: Path):
        return loads(f.read_bytes())

    def dump(self, f: Path, data):
        result = dumps(data)
        if isinstance(result, bytes):
            f.write_bytes(result)
        else:  # pragma: no cover
            f.write_text(result, encoding="utf-8")
