import json
import os
import re
from dataclasses import field
from pathlib import Path
from types import NoneType
from typing import Any, Literal, get_args

from ovld import Medley, call_next, ovld, recurse
from ovld.dependent import Regexp

from ..ctx import AccessPath
from ..exc import NotGivenError, ValidationError
from ..instructions import strip_all
from ..utils import PRIO_HIGH, UnionAlias
from .lazy import LazyProxy
from .partial import Sources


@ovld
def decode_string(t: type[int] | type[float] | type[str], value: str):
    return t(value)


@ovld
def decode_string(t: type[NoneType], value: str):
    val = value.lower()
    if val in ("", "null", "none"):
        return None
    else:
        raise ValidationError(f"Cannot convert '{value}' to None")


@ovld
def decode_string(t: type[bool], value: str):
    val = value.lower()
    if val in ("true", "1", "yes", "on"):
        return True
    elif val in ("false", "0", "no", "off", ""):
        return False
    else:
        raise ValidationError(f"Cannot convert '{value}' to boolean")


@ovld
def decode_string(t: type[object], value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


@ovld
def decode_string(t: type[UnionAlias], value: str):
    err = None
    for opt in get_args(t):
        try:
            return decode_string(opt, value)
        except Exception as exc:
            err = exc
    raise err


@ovld
def decode_string(t: type[list], value: str):
    (element_type,) = get_args(t) or (object,)
    return [recurse(element_type, item.strip()) for item in str(value).split(",")]


class Environment(AccessPath):
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
    def resolve_variable(self, t: Any, expr: str, /):
        match expr.split(":", 1):
            case (method, expr):
                return recurse(t, method, expr)
            case _:
                return recurse(t, "", expr)

    def resolve_variable(self, t: Any, method: Literal[""], expr: str, /):
        return LazyProxy(lambda: self.evaluate_reference(expr))

    def resolve_variable(self, t: Any, method: Literal["env"], expr: str, /):
        try:
            env_value = self.environ[expr]
        except KeyError:
            raise NotGivenError(f"Environment variable '{expr}' is not defined")
        else:
            return decode_string(t, env_value)

    def resolve_variable(self, t: Any, method: Literal["envfile"], expr: str, /):
        try:
            pth = Path(self.environ[expr]).expanduser()
        except KeyError:
            raise NotGivenError(f"Environment variable '{expr}' is not defined")
        if pth.exists():
            return pth
        else:
            return Sources(*[Path(x.strip()).expanduser() for x in str(pth).split(",")])

    def resolve_variable(self, t: Any, method: str, expr: str, /):
        raise ValidationError(
            f"Cannot resolve '{method}:{expr}' because the '{method}' resolver is not defined."
        )


class Interpolation(Medley):
    @ovld(priority=PRIO_HIGH + 0.3)
    def deserialize(self, t: Any, obj: object, ctx: Environment):
        rval = call_next(t, obj, ctx)
        ctx.refs[ctx.access_path] = rval
        return rval

    @ovld(priority=PRIO_HIGH + 0.2)
    def deserialize(self, t: Any, obj: Regexp[r"^\$\{[^}]+\}$"], ctx: Environment):
        expr = obj.lstrip("${").rstrip("}")
        obj = ctx.resolve_variable(strip_all(t), expr)
        if isinstance(obj, LazyProxy):

            def interpolate():
                return recurse(t, obj._obj, ctx)

            return LazyProxy(interpolate)
        else:
            return recurse(t, obj, ctx)

    @ovld(priority=PRIO_HIGH + 0.1)
    def deserialize(self, t: Any, obj: Regexp[r"\$\{[^}]+\}"], ctx: Environment):
        def interpolate():
            def repl(match):
                return str(ctx.resolve_variable(str, match.group(1)))

            subbed = re.sub(r"\$\{([^}]+)\}", repl, obj)
            return recurse(t, subbed, ctx)

        return LazyProxy(interpolate)


# Add as a default feature in serieux.Serieux
__default_features__ = Interpolation
