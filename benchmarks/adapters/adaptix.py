from dataclasses import dataclass

import orjson as json
from adaptix import Retort

from .base import Adapter

_retort = Retort()


@dataclass
class AdaptixAdapter(Adapter):
    def serializer_for_type(self, t):
        return _retort.get_dumper(t)

    def json_for_type(self, t):
        dump = _retort.get_dumper(t)
        return lambda x: json.dumps(dump(x))

    def deserializer_for_type(self, t):
        return _retort.get_loader(t)
