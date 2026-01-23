from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar, get_args

from ovld import Medley, ovld

from ..ctx import Context, WorkingDirectory
from ..instructions import BaseInstruction
from ..priority import HI1, STD
from ..proxy import ProxyBase
from ..tell import tells
from .partial import Partial


@dataclass(frozen=True)
class DefaultFactory(BaseInstruction):
    factory: Callable


T = TypeVar("T")


class FileBacked(Generic[T]):
    path: Path
    value_type: type
    serieux: object
    context: Context
    default_factory: Callable = None
    value: T = None

    def __init__(
        self,
        path: Path,
        value_type: type,
        serieux: object,
        context: Context,
        default_factory: Callable = None,
    ):
        self.path = path
        value_type, df = DefaultFactory.decompose(value_type)
        value_type = Partial.strip(value_type)
        self.value_type = value_type
        self.serieux = serieux
        self.context = context
        self.default_factory = default_factory or (df and df.factory)
        self.value = None
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

    @classmethod
    def serieux_deserialize(cls, obj, ctx, call_next):
        cls = Partial.strip(cls)
        (vt,) = get_args(cls)
        if isinstance(ctx, WorkingDirectory):
            obj = ctx.directory / obj
        else:
            obj = Path(obj)
        return cls(
            path=obj,
            value_type=vt,
            serieux=call_next.serieux,
            context=ctx,
        )

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        return str(obj.path)

    @classmethod
    def serieux_schema(cls, ctx, call_next):
        return {"type": "string"}


@dataclass(frozen=True)
class FileProxy(BaseInstruction):
    default_factory: Callable | None = None


class FileBackedProxy(ProxyBase):
    __special_attributes__ = {
        *ProxyBase.__special_attributes__,
        "_wrapper",
        "_path",
        "load",
        "save",
    }

    def __init__(self, *args, **kwargs):
        self._wrapper = FileBacked(*args, **kwargs)

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


PRIO = STD.next()


class FileBackedFeature(Medley):
    @ovld(priority=PRIO)
    def serialize(self, t: type[Any @ FileProxy], obj: FileBackedProxy, ctx: Context):
        return str(obj._wrapper.path)

    @ovld(priority=PRIO)
    def deserialize(self, t: type[Any @ FileProxy], obj: str | Path, ctx: Context):
        # Merging doesn't make sense here so Partial will just cause problems
        t = Partial.strip(t)
        value_type, fb = FileProxy.decompose(t)
        return FileBackedProxy(
            Path(obj), value_type, self, ctx, default_factory=fb.default_factory
        )

    @ovld(priority=PRIO)
    def schema(self, t: type[Any @ FileProxy], ctx: Context):
        return {"type": "string"}


@tells.register(priority=HI1.next())
def _(expected: type[Any @ FileProxy], given: type[str]):
    return set()


@tells.register(priority=HI1.next())
def _(expected: type[FileBacked], given: type[str]):
    return set()
