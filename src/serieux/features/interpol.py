import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args

from ovld import Medley, call_next, ovld, recurse
from ovld.dependent import Regexp

from ..ctx import AccessPath, Context
from ..exc import NotGivenError, ValidationError
from .lazy import LazyProxy
from .partial import Sources


@dataclass
class StringEncoded:
    value: str


class Variables(AccessPath):
    refs: dict[tuple[str, ...], object] = field(default_factory=dict, repr=False)
    environ: dict = field(default_factory=lambda: os.environ, repr=False)

    def evaluate_reference(self, ref):
        def try_int(x):
            try:
                return int(x)
            except ValueError:
                return x

        stripped = ref.lstrip(".")
        dots = len(ref) - len(stripped)
        root = () if not dots else self.access_path[:-dots]
        parts = [try_int(x) for x in stripped.split(".")]
        return self.refs[(*root, *parts)]

    @ovld
    def resolve_variable(self, expr: str, /):
        match expr.split(":", 1):
            case (method, expr):
                return recurse(method, expr)
            case _:
                return recurse("", expr)

    def resolve_variable(self, method: Literal[""], expr: str, /):
        return LazyProxy(lambda: self.evaluate_reference(expr))

    def resolve_variable(self, method: Literal["env"], expr: str, /):
        try:
            return StringEncoded(self.environ[expr])
        except KeyError:
            raise NotGivenError(f"Environment variable '{expr}' is not defined")

    def resolve_variable(self, method: Literal["envfile"], expr: str, /):
        try:
            pth = Path(self.environ[expr]).expanduser()
        except KeyError:
            raise NotGivenError(f"Environment variable '{expr}' is not defined")
        if pth.exists():
            return pth
        else:
            return Sources(*[Path(x.strip()).expanduser() for x in str(pth).split(",")])

    def resolve_variable(self, method: str, expr: str, /):
        raise ValidationError(
            f"Cannot resolve '{method}:{expr}' because the '{method}' resolver is not defined."
        )


class VariableInterpolation(Medley):
    @ovld(priority=3)
    def deserialize(self, t: Any, obj: object, ctx: Variables):
        rval = call_next(t, obj, ctx)
        ctx.refs[ctx.access_path] = rval
        return rval

    @ovld(priority=2)
    def deserialize(self, t: Any, obj: Regexp[r"^\$\{[^}]+\}$"], ctx: Variables):
        expr = obj.lstrip("${").rstrip("}")
        obj = ctx.resolve_variable(expr)
        if isinstance(obj, LazyProxy):

            def interpolate():
                return recurse(t, obj._obj, ctx)

            return LazyProxy(interpolate)
        else:
            return recurse(t, obj, ctx)

    @ovld(priority=1)
    def deserialize(self, t: Any, obj: Regexp[r"\$\{[^}]+\}"], ctx: Variables):
        def interpolate():
            def repl(match):
                return str(ctx.resolve_variable(match.group(1)))

            subbed = re.sub(r"\$\{([^}]+)\}", repl, obj)
            return recurse(t, subbed, ctx)

        return LazyProxy(interpolate)

    #####################################
    # Deserialize string-encoded values #
    #####################################

    def deserialize(self, t: type[int], obj: StringEncoded, ctx: Context):
        return int(obj.value)

    def deserialize(self, t: type[str], obj: StringEncoded, ctx: Context):
        return str(obj.value)

    def deserialize(self, t: type[float], obj: StringEncoded, ctx: Context):
        return float(obj.value)

    def deserialize(self, t: type[bool], obj: StringEncoded, ctx: Context):
        val = str(obj.value).lower()
        if val in ("true", "1", "yes", "on"):
            return True
        elif val in ("false", "0", "no", "off"):
            return False
        else:
            raise ValidationError(f"Cannot convert '{obj.value}' to boolean")

    def deserialize(self, t: type[list], obj: StringEncoded, ctx: Context):
        (element_type,) = get_args(t) or (object,)
        return [
            recurse(element_type, StringEncoded(item.strip()), ctx)
            for item in str(obj.value).split(",")
        ]


# Add as a default feature in serieux.Serieux
__default_features__ = VariableInterpolation
