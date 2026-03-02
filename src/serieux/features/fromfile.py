from dataclasses import replace
from pathlib import Path
from typing import Any

from ovld import call_next, ovld, recurse
from ovld.dependent import HasKey

from ..ctx import Context, Sourced, WorkingDirectory
from ..exc import ValidationError
from ..formats import FileSource
from ..priority import HI1, MIN, STD5
from ..utils import clsstring
from .partial import PartialBuilding, Sources

include_field = "$include"


PRIO = STD5.next()


class FromFile(PartialBuilding):
    @ovld(priority=PRIO)
    def deserialize(self, t: Any, obj: FileSource, ctx: Context):
        if isinstance(ctx, WorkingDirectory):
            obj = replace(obj, path=ctx.directory / obj.path.expanduser())
        inner_trail = obj.field.split(".") if obj.field else ()
        data = obj.load()
        ctx = ctx + Sourced(
            origin=obj.path,
            directory=obj.path.parent.absolute(),
            format=obj.format,
            source_trail=getattr(ctx, "trail", ()),
            inner_trail=tuple(inner_trail),
        )
        return recurse(t, data, ctx)

    @ovld(priority=PRIO)
    def deserialize(self, t: Any, obj: Path, ctx: Context):
        return recurse(t, FileSource(obj), ctx)


class IncludeFile(FromFile):
    @ovld(priority=HI1)
    def deserialize(self, t: Any, obj: HasKey[include_field], ctx: Context):
        obj = dict(obj)
        paths = recurse(FileSource | list[FileSource], obj.pop(include_field), ctx)
        match paths:
            case [pth] | (FileSource() as pth):
                if obj:
                    return recurse(t, Sources(pth, obj), ctx)
                else:
                    return recurse(t, pth, ctx)
            case _:
                if obj:  # pragma: no cover
                    return recurse(t, Sources(*paths, obj), ctx)
                else:
                    return recurse(t, Sources(*paths), ctx)

    @ovld(priority=MIN)
    def deserialize(self, t: Any, obj: str, ctx: WorkingDirectory):
        if "." not in obj or obj.rsplit(".", 1)[1].isnumeric():
            return call_next(t, obj, ctx)

        src = recurse(FileSource, obj, ctx)
        src = replace(src, path=ctx.directory / src.path)

        if src.path.exists():
            return recurse(t, src, ctx)
        else:
            raise ValidationError(
                f"Tried to read {obj!r} as a configuration file (at path '{src.path}')"
                f" to deserialize into object of type {clsstring(t)},"
                " but there was no such file."
            )
