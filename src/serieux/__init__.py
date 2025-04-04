from .exc import ValidationError, ValidationExceptionGroup
from .impl import BaseImplementation
from .partial import PartialFeature

Serieux = BaseImplementation + PartialFeature
serieux = Serieux()
serialize = serieux.serialize
deserialize = serieux.deserialize
schema = serieux.schema


__all__ = [
    "BaseImplementation",
    "serialize",
    "deserialize",
    "schema",
    "Serieux",
    "serieux",
    "ValidationError",
    "ValidationExceptionGroup",
]
