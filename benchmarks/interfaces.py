import marshmallow_dataclass
import orjson as json
from apischema import deserialize as apischema_deserialize
from apischema import serialize as apischema_serialize
from mashumaro.codecs.basic import BasicDecoder, BasicEncoder
from mashumaro.codecs.orjson import ORJSONEncoder
from pydantic import TypeAdapter

from serieux.deserialization import default as deser_default
from serieux.serialization import default as ser_default


class SerieuxInterface:
    __name__ = "serieux"

    def serializer_for_type(self, t):
        func = ser_default.transform.resolve_for_types(t)
        return func.__get__(ser_default, type(ser_default))

    def json_for_type(self, t):
        func = ser_default.transform.resolve_for_types(t)
        return lambda x: json.dumps(func(ser_default, x))

    def deserializer_for_type(self, t):
        func = deser_default.transform.resolve_for_types(type[t], t)
        return lambda x: func(deser_default, t, x)


serieux = SerieuxInterface()


class ApischemaInterface:
    __name__ = "apischema"

    def serializer_for_type(self, t):
        return lambda x: apischema_serialize(t, x, check_type=False)

    def json_for_type(self, t):
        return lambda x: json.dumps(apischema_serialize(t, x, check_type=False))

    def deserializer_for_type(self, t):
        return lambda x: apischema_deserialize(t, x)


apischema = ApischemaInterface()


class PydanticInterface:
    __name__ = "pydantic"

    def serializer_for_type(self, t):
        return TypeAdapter(t).serializer.to_python

    def json_for_type(self, t):
        return TypeAdapter(t).serializer.to_json

    def deserializer_for_type(self, t):
        return TypeAdapter(t).validator.validate_python


pydantic = PydanticInterface()


class MarshmallowInterface:
    __name__ = "marshmallow"

    def serializer_for_type(self, t):
        schema = marshmallow_dataclass.class_schema(t)()
        return lambda x: schema.dump(x)

    def json_for_type(self, t):
        schema = marshmallow_dataclass.class_schema(t)()
        return lambda x: json.dumps(schema.dump(x))

    def deserializer_for_type(self, t):
        schema = marshmallow_dataclass.class_schema(t)()
        return lambda x: schema.load(x)


marshmallow = MarshmallowInterface()


class MashumaroInterface:
    __name__ = "mashumaro"

    def serializer_for_type(self, t):
        return BasicEncoder(t).encode

    def json_for_type(self, t):
        return ORJSONEncoder(t).encode

    def deserializer_for_type(self, t):
        return BasicDecoder(t).decode


mashumaro = MashumaroInterface()
