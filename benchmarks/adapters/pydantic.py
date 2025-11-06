from dataclasses import dataclass

from pydantic import TypeAdapter

from .base import Adapter


@dataclass
class PydanticAdapter(Adapter):
    def serializer_for_type(self, t):
        return TypeAdapter(t).serializer.to_python

    def json_for_type(self, t):
        return TypeAdapter(t).serializer.to_json

    def deserializer_for_type(self, t):
        return TypeAdapter(t).validator.validate_python
