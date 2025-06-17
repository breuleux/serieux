import importlib
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from .auto import Auto
from .ctx import AccessPath, Context, Patch, Patcher
from .exc import SerieuxError, ValidationError, ValidationExceptionGroup
from .features.clargs import CLIDefinition, CommandLineArguments, parse_cli
from .features.dotted import DottedNotation
from .features.fromfile import FromFileExtra, WorkingDirectory
from .features.interpol import Environment
from .features.lazy import DeepLazy, Lazy, LazyProxy
from .features.partial import Partial, Sources
from .features.registered import Registered, StringMapped, singleton
from .features.tagged import Tagged, TaggedUnion
from .features.tsubclass import TaggedSubclass
from .impl import BaseImplementation
from .instructions import InstructionType, NewInstruction
from .model import Extensible, FieldModelizable, Model, Modelizable, StringModelizable
from .schema import RefPolicy, Schema
from .utils import JSON, check_signature
from .version import version as __version__


def _default_features():
    # Collect features declared in the __default_features__ global variables of the features
    # in features/. To see which ones this is on a cloned repo, you can run:
    # $ git grep __default_features__
    here = Path(__file__).parent
    features = []
    for name in (here / "features").glob("*.py"):
        if not name.stem.startswith("_"):
            mod = importlib.import_module(f"{__spec__.name}.features.{name.stem}")
            if feat := getattr(mod, "__default_features__", None):
                features.append(feat)
    features.sort(key=lambda t: -len(t.mro()))
    return features


default_features = _default_features()


if TYPE_CHECKING:  # pragma: no cover
    from typing import TypeVar

    T = TypeVar("T")

    JSON = list["JSON"] | dict[str, "JSON"] | int | str | float | bool | None

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


__all__ = [
    "__version__",
    "AccessPath",
    "Auto",
    "BaseImplementation",
    "CLIDefinition",
    "CommandLineArguments",
    "Context",
    "DeepLazy",
    "deserialize",
    "DottedNotation",
    "dump",
    "Environment",
    "Extensible",
    "FromFileExtra",
    "InstructionType",
    "JSON",
    "Lazy",
    "LazyProxy",
    "load",
    "Model",
    "FieldModelizable",
    "Modelizable",
    "NewInstruction",
    "parse_cli",
    "Partial",
    "Patch",
    "Patcher",
    "RefPolicy",
    "Registered",
    "schema",
    "Schema",
    "serialize",
    "serieux",
    "Serieux",
    "SerieuxError",
    "singleton",
    "Sources",
    "StringMapped",
    "StringModelizable",
    "Tagged",
    "TaggedUnion",
    "TaggedSubclass",
    "ValidationError",
    "ValidationExceptionGroup",
    "WorkingDirectory",
]
