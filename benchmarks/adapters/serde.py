from dataclasses import dataclass

from serde.de import from_dict as serde_from_dict
from serde.json import to_json as serde_to_json
from serde.se import to_dict as serde_to_dict

from .base import Adapter


@dataclass
class SerdeAdapter(Adapter):
    def serializer_for_type(self, t):
        return serde_to_dict

    def json_for_type(self, t):
        return serde_to_json

    def deserializer_for_type(self, t):
        return lambda x: serde_from_dict(t, x)
