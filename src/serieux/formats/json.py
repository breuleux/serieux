from functools import partial

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
    def loads(self, s: str):
        return loads(s)

    def dumps(self, data):
        result = dumps(data)
        if isinstance(result, bytes):
            result = result.decode("utf-8")
        return result
