from .ctx import Context
from .exc import ValidationError, ValidationExceptionGroup
from .impl import BaseImplementation
from .partial import PartialFeature
from .typetags import NewTag, TaggedType

Serieux = BaseImplementation + PartialFeature
serieux = Serieux()
serialize = serieux.serialize
deserialize = serieux.deserialize
schema = serieux.schema


__all__ = [
    "Context",
    "NewTag",
    "TaggedType",
    "BaseImplementation",
    "serialize",
    "deserialize",
    "schema",
    "Serieux",
    "serieux",
    "ValidationError",
    "ValidationExceptionGroup",
]
