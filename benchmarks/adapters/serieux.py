from dataclasses import dataclass

import orjson as json

from serieux import get_deserializer, get_serializer

from .base import Adapter


@dataclass
class SerieuxAdapter(Adapter):
    def serializer_for_type(self, t):
        return get_serializer(t)

    def json_for_type(self, t):
        func = get_serializer(t)
        return lambda x: json.dumps(func(x))

    def deserializer_for_type(self, t):
        return get_deserializer(t)
