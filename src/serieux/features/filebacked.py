import time
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
    timestamp: float = None
    refresh: bool = False
    default_factory: Callable = None
    value: T = None

    def __init__(
        self,
        path: Path,
        value_type: type,
        serieux: object,
        context: Context,
        refresh: bool = False,
        default_factory: Callable = None,
    ):
        self.path = path
        value_type, df = DefaultFactory.decompose(value_type)
        value_type = Partial.strip(value_type)
        self.value_type = value_type
        self.serieux = serieux
        self.context = context
        self.refresh = refresh
        self.default_factory = default_factory or (df and df.factory)
        self._value = None
        self.timestamp = None
        self.load()

    @property
    def value(self):
        if self.refresh and self.path.exists():
            file_mtime = self.path.stat().st_mtime
            if file_mtime > self.timestamp:
                self.load()
        return self._value

    def load(self):
        if self.path.exists():
            self._value = self.serieux.deserialize(self.value_type, self.path, self.context)
            self.timestamp = self.path.stat().st_mtime
        elif self.default_factory:
            self._value = self.default_factory()
            self.timestamp = time.time()
        else:
            raise FileNotFoundError(self.path)

    def save(self):
        self.serieux.dump(self.value_type, self._value, self.context, dest=self.path)
        self.timestamp = time.time()

    def __str__(self):
        return f"{self._value}@{self.path}"

    __repr__ = __str__

    @classmethod
    def serieux_deserialize(cls, obj, ctx, call_next):
        cls = Partial.strip(cls)
        cls, fopt = FileBackedOptions.decompose(cls)
        (vt,) = get_args(cls)
        if isinstance(ctx, WorkingDirectory):
            obj = ctx.directory / obj
        else:
            obj = Path(obj)
        extra = vars(fopt) if fopt else {}
        return cls(
            path=obj,
            value_type=vt,
            serieux=call_next.serieux,
            context=ctx,
            **extra,
        )

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        return str(obj.path)

    @classmethod
    def serieux_schema(cls, ctx, call_next):
        return {"type": "string"}


@dataclass(frozen=True)
class FileBackedOptions(BaseInstruction):
    default_factory: Callable | None = None
    refresh: bool = False


@dataclass(frozen=True)
class FileProxy(FileBackedOptions):
    pass


class FileBackedProxy(ProxyBase):
    __special_attributes__ = {
        *ProxyBase.__special_attributes__,
        "_wrapper",
        "_path",
        "load",
        "save",
    }

    def __init__(self, path, value_type, *args, **kwargs):
        self._wrapper = FileBacked(path, value_type, *args, **kwargs)
        self._type = value_type

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
            Path(obj),
            value_type,
            self,
            ctx,
            default_factory=fb.default_factory,
            refresh=fb.refresh,
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
