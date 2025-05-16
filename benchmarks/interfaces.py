import marshmallow_dataclass
import orjson as json
from apischema import deserialize as apischema_deserialize, serialize as apischema_serialize
from mashumaro.codecs.basic import BasicDecoder, BasicEncoder
from mashumaro.codecs.orjson import ORJSONEncoder
from pydantic import TypeAdapter
from serde.de import from_dict as serde_from_dict
from serde.json import to_json as serde_to_json
from serde.se import to_dict as serde_to_dict

from serieux import deserialize as serieux_deserialize, serialize as serieux_serialize, serieux
from serieux.ctx import EmptyContext, empty


class SerieuxInterface:
    __name__ = "serieux"

    def serializer_for_type(self, t):
        func = serieux_serialize.resolve(type[t], t, EmptyContext)
        return lambda x: func(serieux, t, x, empty)

    def json_for_type(self, t):
        func = serieux_serialize.resolve(type[t], t, EmptyContext)
        return lambda x: json.dumps(func(serieux, t, x, empty))

    def deserializer_for_type(self, t):
        func = serieux_deserialize.resolve(type[t], dict, EmptyContext)
        return lambda x: func(serieux, t, x, empty)


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


class SerdeInterface:
    __name__ = "serde"

    def serializer_for_type(self, t):
        return serde_to_dict

    def json_for_type(self, t):
        return serde_to_json

    def deserializer_for_type(self, t):
        return lambda x: serde_from_dict(t, x)


serde = SerdeInterface()
