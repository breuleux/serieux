import inspect
from dataclasses import dataclass
from functools import partial

from ovld import Ovld

from .base import standard_code_generator
from .deserialization import Deserializer
from .serialization import Serializer


class Module:
    def __init__(self):
        self.serializers = Ovld()
        self.deserializers = Ovld()

    def _add(self, fn, *, field, priority=0, codegen=False):
        if fn is None:
            return partial(self._add, field=field, priority=priority, codegen=codegen)

        if list(inspect.signature(fn).parameters)[0] != "self":  # pragma: no cover
            raise TypeError("The first argument to a (de)serializer must be `self`.")

        if codegen:
            fn = standard_code_generator(fn)
        getattr(self, field).register(fn, priority=priority)

    def deserializer(self, fn=None, *, priority=0, codegen=False):
        return self._add(field="deserializers", fn=fn, priority=priority, codegen=codegen)

    def serializer(self, fn=None, *, priority=0, codegen=False):
        return self._add(field="serializers", fn=fn, priority=priority, codegen=codegen)


@dataclass
class Interface:
    _serializer: Serializer
    _deserializer: Deserializer

    def __post_init__(self):
        self.serialize = self._serializer.transform
        self.deserialize = self._deserializer.transform


def create(*modules, validate_serialization=None, validate_deserialization=None):
    sovld = Ovld(
        name="serialize",
        mixins=[Serializer.transform] + [m.serializers for m in modules],
    )
    NewSerializer = type("Serializer", (Serializer,), {"transform": sovld})

    dovld = Ovld(
        name="deserialize",
        mixins=[Deserializer.transform] + [m.deserializers for m in modules],
    )
    NewDeserializer = type("Deserializer", (Deserializer,), {"transform": dovld})

    return Interface(
        _serializer=NewSerializer(validate=validate_serialization),
        _deserializer=NewDeserializer(validate=validate_deserialization),
    )
