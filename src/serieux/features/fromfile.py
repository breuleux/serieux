from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ovld import call_next, ovld, recurse
from ovld.dependent import HasKey

from .. import formats
from ..ctx import Context, Sourced, WorkingDirectory
from ..exc import ValidationError
from ..formats.abc import FileFormat
from ..priority import MIN
from ..utils import clsstring
from .partial import PartialBuilding, Sources

include_field = "$include"


@dataclass
class PathAndFormat:
    path: Path
    format: FileFormat = None

    def __post_init__(self):
        if not isinstance(self.format, FileFormat):
            self.format = formats.find(self.path, suffix=self.format)

    @classmethod
    def serieux_from_string(cls, incl):
        return cls(Path(incl))


class FromFile(PartialBuilding):
    def deserialize(self, t: Any, obj: PathAndFormat, ctx: Context):
        pth = obj.path
        if isinstance(ctx, WorkingDirectory):
            pth = ctx.directory / pth.expanduser()
        try:
            data = obj.format.load(pth)
        except Exception as exc:
            raise ValidationError(f"Could not read data from file '{pth}'", exc=exc, ctx=ctx)
        ctx = ctx + Sourced(
            origin=pth,
            directory=pth.parent,
            format=obj.format,
            source_access_path=getattr(ctx, "access_path", ()),
        )
        return recurse(t, data, ctx)

    def deserialize(self, t: Any, obj: Path, ctx: Context):
        return recurse(t, PathAndFormat(obj), ctx)


class IncludeFile(FromFile):
    @ovld(priority=1)
    def deserialize(self, t: type[object], obj: HasKey[include_field], ctx: Context):
        obj = dict(obj)
        paths = recurse(PathAndFormat | list[PathAndFormat], obj.pop(include_field), ctx)
        match paths:
            case [pth] | (PathAndFormat() as pth):
                if obj:
                    return recurse(t, Sources(pth, obj), ctx)
                else:
                    return recurse(t, pth, ctx)
            case _:
                return recurse(t, Sources(*paths, obj), ctx)

    @ovld(priority=MIN)
    def deserialize(self, t: type[object], obj: str, ctx: WorkingDirectory):
        if "." not in obj or obj.rsplit(".", 1)[1].isnumeric():
            return call_next(t, obj, ctx)

        path = ctx.directory / obj
        if path.exists():
            return recurse(t, path, ctx)
        else:
            raise ValidationError(
                f"Tried to read '{obj}' as a configuration file (at path '{path}')"
                f" to deserialize into object of type {clsstring(t)},"
                " but there was no such file."
            )
