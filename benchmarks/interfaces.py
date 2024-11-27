from apischema import serialize as apischema_serialize
from serieux import serialize as serieux_serialize
from pydantic import TypeAdapter
import marshmallow_dataclass
import orjson as json
from mashumaro.codecs.json import JSONDecoder, JSONEncoder


class SerieuxInterface:
    __name__ = "serieux"

    def serializer_for_type(self, t):
        return lambda x: serieux_serialize(t, x)

    def json_for_type(self, t):
        return lambda x: json.dumps(serieux_serialize(t, x))


serieux = SerieuxInterface()


class ApischemaInterface:
    __name__ = "apischema"

    def serializer_for_type(self, t):
        return lambda x: apischema_serialize(t, x)

    def json_for_type(self, t):
        return lambda x: json.dumps(apischema_serialize(t, x))


apischema = ApischemaInterface()


class PydanticInterface:
    __name__ = "pydantic"

    def serializer_for_type(self, t):
        adapter = TypeAdapter(t)
        return lambda x: json.loads(adapter.serializer.to_json(x))

    def json_for_type(self, t):
        adapter = TypeAdapter(t)
        return lambda x: adapter.serializer.to_json(x)


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
        schema = JSONEncoder(t)
        return lambda x: json.loads(schema.encode(x))

    def json_for_type(self, t):
        schema = JSONEncoder(t)
        return lambda x: schema.encode(x)


mashumaro = MashumaroInterface()
