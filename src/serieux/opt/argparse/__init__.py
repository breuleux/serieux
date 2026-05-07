from __future__ import annotations

import sys
from dataclasses import dataclass, field, make_dataclass
from typing import Any

from ovld import Medley, ovld, recurse
from ovld.utils import clsstring

from ...ctx import Context
from ...features.dotted import unflatten
from ...linearize import GroupState, linearize
from .errors import ParseError
from .parse import CliParser, Control, Word
from .tokenize import tokenize


@dataclass
class CommandLineArguments:
    """Wrapper around an argv list, consumed by :class:`FromArguments`."""

    arguments: list[str] = None
    prog: str = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = sys.argv[1:]
        if self.prog is None:
            self.prog = sys.argv[0]


class FromArguments(Medley):
    """Serieux Medley that allows deserializing any type directly from CLI args."""

    @ovld(priority=1)
    def deserialize(self, t: type[int], obj: Word, ctx: Context):
        return int(obj.value)

    @ovld(priority=1)
    def deserialize(self, t: type[float], obj: Word, ctx: Context):
        return float(obj.value)

    @ovld(priority=1)
    def deserialize(self, t: Any, obj: Word, ctx: Context):
        return recurse(t, obj.value)

    @ovld(priority=1)
    def deserialize(self, t: Any, obj: CommandLineArguments, ctx: Context):
        augmented_type = make_dataclass(
            cls_name=f"Args_{clsstring(t)}",
            bases=(),
            fields=[
                ("__value", t, field(metadata={"description": "Options"})),
                ("__control", Control, field(metadata={"description": "Meta-options"})),
            ],
        )

        tokens = tokenize(obj.arguments, prog=obj.prog)
        root_group = linearize(augmented_type)
        gs = GroupState(root_group)
        parser = CliParser(
            gs, prog=obj.prog, argv=obj.arguments, deserialize=self.deserialize, root_type=t
        )
        result = parser.run(tokens)
        vals = unflatten(result, allow_lists=True)

        control = recurse(Control, vals.get("__control", {}))
        vals = control.build(parser, vals.get("__value", {}))

        try:
            return recurse(t, vals, ctx)
        except ParseError:
            raise
        except Exception as exc:
            # Try to attach a source location from spans
            try:
                from ...exc import find_information

                info = find_information(exc=exc, ctx=ctx)
                path = ".".join(str(p) for p in info.path)
                if loc := vals.spans.get(path):
                    raise ParseError(str(exc), loc) from None
            except Exception:
                pass
            raise


__all__ = [
    "CommandLineArguments",
    "FromArguments",
    "ParseError",
]
