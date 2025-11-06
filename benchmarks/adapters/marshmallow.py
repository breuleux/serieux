from dataclasses import dataclass

import marshmallow_dataclass
import orjson as json

from .base import Adapter


@dataclass
class MarshmallowAdapter(Adapter):
    def serializer_for_type(self, t):
        schema = marshmallow_dataclass.class_schema(t)()
        return schema.dump

    def json_for_type(self, t):
        schema = marshmallow_dataclass.class_schema(t)()
        return lambda x: json.dumps(schema.dump(x))

    def deserializer_for_type(self, t):
        schema = marshmallow_dataclass.class_schema(t)()
        return schema.load
