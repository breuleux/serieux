from .core import DataConverter
from .exc import ValidationError, ValidationExceptionGroup

default_converter = DataConverter()

serialize = default_converter.serialize
deserialize = default_converter.deserialize
deserialize_partial = default_converter.deserialize_partial
schema = default_converter.schema
model = default_converter.model

__all__ = [
    "DataConverter",
    "serialize",
    "deserialize",
    "deserialize_partial",
    "schema",
    "model",
    "ValidationError",
    "ValidationExceptionGroup",
]
