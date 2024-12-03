import marshmallow_dataclass
import orjson as json
from apischema import serialize as apischema_serialize
from mashumaro.codecs.basic import BasicEncoder
from mashumaro.codecs.orjson import ORJSONEncoder
from pydantic import TypeAdapter

from serieux import default_converter
from serieux.serialization import default


class SerieuxInterface:
    __name__ = "serieux"

    def serializer_for_type(self, t):
        func = default.serialize.resolve_for_types(t)
        return func.__get__(default_converter, type(default_converter))

    def json_for_type(self, t):
        func = default.serialize.resolve_for_types(t)
        return lambda x: json.dumps(func(None, x))


serieux = SerieuxInterface()


class OldSerieuxInterface:
    __name__ = "old_serieux"

    def serializer_for_type(self, t):
        fn = default_converter.serialize
        return lambda x: fn(t, x)

    def json_for_type(self, t):
        fn = default_converter.serialize
        return lambda x: json.dumps(fn(t, x))


old_serieux = OldSerieuxInterface()


class ApischemaInterface:
    __name__ = "apischema"

    def serializer_for_type(self, t):
        return lambda x: apischema_serialize(t, x, check_type=False)

    def json_for_type(self, t):
        return lambda x: json.dumps(apischema_serialize(t, x, check_type=False))


apischema = ApischemaInterface()


class PydanticInterface:
    __name__ = "pydantic"

    def serializer_for_type(self, t):
        return TypeAdapter(t).serializer.to_python

    def json_for_type(self, t):
        return TypeAdapter(t).serializer.to_json


pydantic = PydanticInterface()


class MarshmallowInterface:
    __name__ = "marshmallow"

    def serializer_for_type(self, t):
        schema = marshmallow_dataclass.class_schema(t)()
        return lambda x: schema.dump(x)

    def json_for_type(self, t):
        schema = marshmallow_dataclass.class_schema(t)()
        return lambda x: json.dumps(schema.dump(x))


marshmallow = MarshmallowInterface()


class MashumaroInterface:
    __name__ = "mashumaro"

    def serializer_for_type(self, t):
        return BasicEncoder(t).encode

    def json_for_type(self, t):
        return ORJSONEncoder(t).encode


mashumaro = MashumaroInterface()
