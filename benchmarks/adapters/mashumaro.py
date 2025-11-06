from dataclasses import dataclass

from mashumaro.codecs.basic import BasicDecoder, BasicEncoder
from mashumaro.codecs.orjson import ORJSONEncoder

from .base import Adapter


@dataclass
class MashumaroAdapter(Adapter):
    def serializer_for_type(self, t):
        return BasicEncoder(t).encode

    def json_for_type(self, t):
        return ORJSONEncoder(t).encode

    def deserializer_for_type(self, t):
        return BasicDecoder(t).decode
