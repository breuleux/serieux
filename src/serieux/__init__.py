from .ctx import Context
from .exc import ValidationError, ValidationExceptionGroup
from .features.lazy import DeepLazy, Lazy, LazyDeserialization, LazyProxy
from .features.partial import PartialBuilding, Sources
from .impl import BaseImplementation
from .typetags import NewTag, TaggedType
from .version import version as __version__

Serieux = BaseImplementation + PartialBuilding + LazyDeserialization
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
    "Sources",
    "ValidationError",
    "ValidationExceptionGroup",
    "Lazy",
    "DeepLazy",
    "LazyProxy",
    "__version__",
]
