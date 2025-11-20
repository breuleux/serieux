from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ovld import Medley

from ..ctx import Context
from ..instructions import BaseInstruction
from ..proxy import ProxyBase
from ..tell import tells
from .partial import Partial


@dataclass(frozen=True)
class FileBacked(BaseInstruction):
    default_factory: Callable | None = None
    proxy: bool = False


@dataclass
class BackedObject:
    path: Path
    value_type: type
    serieux: object
    context: Context
    default_factory: Callable = None
    value: object = None

    def __post_init__(self):
        self.load()

    def load(self):
        if self.path.exists():
            self.value = self.serieux.deserialize(self.value_type, self.path, self.context)
        elif self.default_factory:
            self.value = self.default_factory()
        else:
            raise FileNotFoundError(self.path)

    def save(self):
        self.serieux.dump(self.value_type, self.value, self.context, dest=self.path)

    def __str__(self):
        return f"{self.value}@{self.path}"

    __repr__ = __str__


class BackedProxy(ProxyBase):
    __special_attributes__ = {
        *ProxyBase.__special_attributes__,
        "_wrapper",
        "_path",
        "load",
        "save",
    }

    def __init__(self, *args, **kwargs):
        self._wrapper = BackedObject(*args, **kwargs)

    @property
    def _obj(self):
        return self._wrapper.value

    @property
    def _path(self):
        return self._wrapper.path

    def load(self):
        return self._wrapper.load()

    def save(self):
        return self._wrapper.save()

    def __str__(self):
        return str(self._wrapper)

    __repr__ = __str__


class FileBackedFeature(Medley):
    def serialize(self, t: type[Any @ FileBacked], obj: BackedObject, ctx: Context):
        return str(obj.path)

    def serialize(self, t: type[Any @ FileBacked], obj: BackedProxy, ctx: Context):
        return str(obj._wrapper.path)

    def deserialize(self, t: type[Any @ FileBacked], obj: str | Path, ctx: Context):
        # Merging doesn't make sense here so Partial will just cause problems
        t = Partial.strip(t)
        value_type, fb = FileBacked.decompose(t)
        constructor = BackedProxy if fb.proxy else BackedObject
        return constructor(Path(obj), value_type, self, ctx, default_factory=fb.default_factory)

    def schema(self, t: type[Any @ FileBacked], ctx: Context):
        return {"type": "string"}


@tells.register
def _(expected: type[Any @ FileBacked], given: type[str]):
    return set()
