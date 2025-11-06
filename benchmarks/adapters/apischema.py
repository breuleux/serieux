from dataclasses import dataclass

import orjson as json
from apischema import deserialize as apischema_deserialize, serialize as apischema_serialize

from .base import Adapter


@dataclass
class ApischemaAdapter(Adapter):
    def serializer_for_type(self, t):
        return lambda x: apischema_serialize(t, x, check_type=False)

    def json_for_type(self, t):
        return lambda x: json.dumps(apischema_serialize(t, x, check_type=False))

    def deserializer_for_type(self, t):
        return lambda x: apischema_deserialize(t, x)
