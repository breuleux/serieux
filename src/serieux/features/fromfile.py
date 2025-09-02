from pathlib import Path
from typing import Any

from ovld import call_next, ovld, recurse
from ovld.dependent import HasKey

from .. import formats
from ..ctx import Context, Sourced, WorkingDirectory
from ..exc import ValidationError
from ..priority import MIN
from ..utils import clsstring
from .partial import PartialBuilding, Sources

include_field = "$include"


class FromFile(PartialBuilding):
    def deserialize(self, t: Any, obj: Path, ctx: Context):
        if isinstance(ctx, WorkingDirectory):
            obj = ctx.directory / obj.expanduser()
        try:
            fmt = formats.find(obj)
            data = fmt.load(obj)
        except Exception as exc:
            raise ValidationError(f"Could not read data from file '{obj}'", exc=exc, ctx=ctx)
        ctx = ctx + Sourced(origin=obj, directory=obj.parent, format=fmt)
        return recurse(t, data, ctx)


class IncludeFile(FromFile):
    @ovld(priority=1)
    def deserialize(self, t: type[object], obj: HasKey[include_field], ctx: Context):
        obj = dict(obj)
        incl = recurse(str, obj.pop(include_field), ctx)
        if obj:
            return recurse(t, Sources(Path(incl), obj), ctx)
        else:
            return recurse(t, Path(incl), ctx)

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
