import importlib
import importlib.metadata
import logging
import os
import sys
import traceback
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from .auto import Auto
from .ctx import Context, Patch, Patcher, Trail, WorkingDirectory
from .exc import (
    SerieuxError,
    ValidationError,
    ValidationExceptionGroup,
    display_context_information,
)
from .features.clargs import CLIDefinition, CommandLineArguments, parse_cli
from .features.comment import Comment, CommentRec
from .features.dotted import DottedNotation
from .features.fromfile import IncludeFile
from .features.interpol import Environment
from .features.lazy import DeepLazy, Lazy, LazyProxy
from .features.partial import AllTrails, Partial, Sources
from .features.registered import AutoRegistered, Referenced, auto_singleton
from .features.tagset import ReferencedClass, Tagged, TaggedSubclass, TaggedUnion
from .impl import BaseImplementation
from .instructions import Instruction
from .model import AllowExtras, Field, FieldModelizable, Model, Modelizable, StringModelizable
from .schema import RefPolicy, Schema
from .utils import JSON, check_signature
from .version import version as __version__

logger = logging.getLogger("serieux")


def _default_features():
    features = []
    eps = importlib.metadata.entry_points(group="serieux.default_features")
    for ep in eps:
        try:
            feature = ep.load()
        except ImportError:  # pragma: no cover
            # Some features may be dependent on what packages are installed.
            # That is fine.
            continue
        except Exception:  # pragma: no cover
            logger.warning(
                "Default serieux feature %r (%s) failed to load:\n%s",
                ep.name,
                ep.value,
                traceback.format_exc(),
            )
        else:
            features.append(feature)
    features.sort(key=lambda t: -len(t.mro()))
    return features


default_features = _default_features()


if TYPE_CHECKING:  # pragma: no cover
    from typing import TypeVar

    T = TypeVar("T")

    JSON: TypeAlias = list["JSON"] | dict[str, "JSON"] | int | str | float | bool | None

    class _MC:
        def __add__(self, other) -> type["Serieux"]: ...

    class Serieux(metaclass=_MC):
        def dump(
            self, t: type[T], obj: object, ctx: Context = None, *, dest: Path = None
        ) -> JSON | None: ...

        def load(self, t: type[T], obj: object, ctx: Context = None) -> T: ...

        def serialize(self, t: type[T], obj: object, ctx: Context = None) -> JSON: ...

        def deserialize(self, t: type[T], obj: object, ctx: Context = None) -> T: ...

        def schema(self, t: type[T], ctx: Context = None) -> Schema[str, "JSON"]: ...

        def __add__(self, other) -> "Serieux": ...

else:

    class Serieux(BaseImplementation, *default_features):
        pass


serieux = Serieux()
serialize = serieux.serialize
deserialize = serieux.deserialize
schema = serieux.schema
load = serieux.load
dump = serieux.dump
get_serializer = serieux.get_serializer
get_deserializer = serieux.get_deserializer


def serializer(fn=None, priority=0):
    if fn is None:
        return partial(serializer, priority=priority)

    check_signature(fn, "serializer", ("self", "t: type[T1]", "obj: T2", "ctx: T3>Context"))
    Serieux.serialize.register(fn, priority=priority)
    return fn


def deserializer(fn=None, priority=0):
    if fn is None:
        return partial(deserializer, priority=priority)

    check_signature(fn, "deserializer", ("self", "t: type[T1]", "obj: T2", "ctx: T3>Context"))
    Serieux.deserialize.register(fn, priority=priority)
    return fn


def schema_definition(fn=None, priority=0):
    if fn is None:
        return partial(schema_definition, priority=priority)

    check_signature(fn, "schema definition", ("self", "t: type[T1]", "ctx: T2>Context"))
    Serieux.schema.register(fn, priority=priority)
    return fn


if sys.excepthook is sys.__excepthook__ and not os.getenv("SERIEUX_DISABLE_EXCEPTHOOK", None):

    def custom_excepthook(exc_type, exc_value, exc_traceback):  # pragma: no cover
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        display_context_information(exc=exc_value)

    sys.excepthook = custom_excepthook


__all__ = [
    "__version__",
    "AllowExtras",
    "AllTrails",
    "Auto",
    "AutoRegistered",
    "auto_singleton",
    "BaseImplementation",
    "CLIDefinition",
    "CommandLineArguments",
    "Comment",
    "CommentRec",
    "Context",
    "DeepLazy",
    "deserialize",
    "display_context_information",
    "DottedNotation",
    "dump",
    "Environment",
    "Field",
    "get_deserializer",
    "get_serializer",
    "IncludeFile",
    "JSON",
    "Lazy",
    "LazyProxy",
    "load",
    "Model",
    "FieldModelizable",
    "Modelizable",
    "Instruction",
    "parse_cli",
    "Partial",
    "Patch",
    "Patcher",
    "RefPolicy",
    "Referenced",
    "ReferencedClass",
    "Registered",
    "schema",
    "Schema",
    "serialize",
    "serieux",
    "Serieux",
    "SerieuxError",
    "Sources",
    "StringModelizable",
    "Tagged",
    "TaggedUnion",
    "TaggedSubclass",
    "Trail",
    "ValidationError",
    "ValidationExceptionGroup",
    "WorkingDirectory",
]
