import importlib
from pathlib import Path
from typing import TYPE_CHECKING

from .auto import Auto
from .ctx import Context
from .exc import ValidationError, ValidationExceptionGroup
from .features.clargs import CommandLineArguments
from .features.lazy import DeepLazy, Lazy, LazyProxy
from .features.partial import Sources
from .features.tagged import Tagged
from .impl import BaseImplementation
from .instructions import InstructionType, NewInstruction
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
    return features


default_features = _default_features()


if TYPE_CHECKING:  # pragma: no cover
    from typing import TypeVar

    from .schema import Schema

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


__all__ = [
    "__version__",
    "Auto",
    "BaseImplementation",
    "CommandLineArguments",
    "Context",
    "DeepLazy",
    "deserialize",
    "dump",
    "InstructionType",
    "Lazy",
    "LazyProxy",
    "load",
    "NewInstruction",
    "schema",
    "serialize",
    "serieux",
    "Serieux",
    "Sources",
    "Tagged",
    "ValidationError",
    "ValidationExceptionGroup",
]
