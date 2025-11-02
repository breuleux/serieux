import json
import os
import re
from dataclasses import field
from pathlib import Path
from types import NoneType
from typing import Annotated, Any, Literal, get_args

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Trail
from ..exc import NotGivenError, ValidationError
from ..instructions import strip
from ..priority import HI1
from ..utils import UnionAlias
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


@ovld
def decode_string(t: type[Annotated], value: str):
    return recurse(strip(t), value)


class Environment(Trail):
    refs: dict[tuple[str, ...], object] = field(default_factory=dict, repr=False)
    environ: dict = field(default_factory=lambda: os.environ, repr=False)
    interpolation_pattern: re.Pattern = re.compile(r"\$\{([^}]+)\}")

    def __post_init__(self):
        if isinstance(self.interpolation_pattern, str):
            self.interpolation_pattern = re.compile(self.interpolation_pattern)

    def evaluate_reference(self, ref):
        def try_int(x):
            try:
                return int(x)
            except ValueError:
                return x

        stripped = ref.lstrip(".")
        dots = len(ref) - len(stripped)
        root = () if not dots else self.trail[:-dots]
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

    def __setitem__(self, pth, value):
        if not isinstance(pth, tuple):
            pth = (pth,)
        self.refs[pth] = value


class Interpolation(Medley):
    @ovld(priority=HI1(3))
    def deserialize(self, t: Any, obj: object, ctx: Environment):
        rval = call_next(t, obj, ctx)
        ctx.refs[ctx.trail] = rval
        return rval

    @ovld(priority=HI1(2))
    def deserialize(self, t: Any, obj: str, ctx: Environment):
        match ctx.interpolation_pattern.split(obj):
            case [s]:
                return call_next(t, s, ctx)
            case ["", expr, ""]:
                obj = ctx.resolve_variable(t, expr)
                if isinstance(obj, LazyProxy):

                    def interpolate():
                        return recurse(t, obj._obj, ctx)

                    return LazyProxy(interpolate)
                else:
                    return recurse(t, obj, ctx)
            case parts:

                def interpolate():
                    resolved = [
                        p if i % 2 == 0 else ctx.resolve_variable(str, p)
                        for i, p in enumerate(parts)
                    ]
                    subbed = "".join(map(str, resolved))
                    return recurse(t, subbed, ctx)

                return LazyProxy(interpolate)
