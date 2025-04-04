import importlib
import sys
import typing
from types import GenericAlias, NoneType, UnionType
from typing import (
    ForwardRef,
    TypeVar,
    Union,
    _GenericAlias,
    get_args,
    get_origin,
)

from ovld import parametrized_class_check

from .proxy import Accessor, Proxy, Source

UnionAlias = type(Union[int, str])


def _color(code, text):
    return f"\u001b[1m\u001b[{code}m{text}\u001b[0m"


def context_string(
    obj,
    message,
    show_source=True,
    source_context=1,
    indent=0,
    ellipsis_cutoff=3,
):
    n = 3 + indent
    if isinstance(obj, Proxy):
        ctx = obj._self_ann
    elif isinstance(obj, dict):
        ctx = obj
    else:
        raise Exception("obj should be a Proxy or a dict")
    acc = ctx.get(Accessor, "??")
    acc_string = str(acc) or "(at root)"
    return_lines = [f"{_color(33, acc_string)}: {message}"]
    if show_source and (location := ctx.get(Source, None)):
        (l1, c1), (l2, c2) = location.linecols
        if c2 == 0:
            l2 -= 1
            c2 = 10_000_000_000_000
        lines = location.source.split("\n")
        start = l1 - source_context
        while start < 0 or not lines[start].strip():
            start += 1
        end = l2 + source_context
        while end >= len(lines) or not lines[end].strip():
            end -= 1

        return_lines.append(f"{'':{indent}}@ {location.origin}:{l1 + 1}")
        for li in range(start, end + 1):
            line = lines[li]
            if li == l2 and not line.strip():
                break
            if li == l1 + ellipsis_cutoff and li < l2:
                return_lines.append(f"{'':{n}}  ...")
                continue
            elif li > l1 + ellipsis_cutoff and li < l2:
                continue

            hls = hle = 0
            if li == l1:
                hls = c1
            if li >= l1 and li < l2:
                hle = len(line)
            if li == l2:
                hle = c2

            if hls or hle:
                line = line[:hls] + _color(31, line[hls:hle]) + line[hle:]

            return_lines.append(f"{li + 1:{n}}: {line}")
    return "\n".join(return_lines)


def display_context(*args, file=sys.stdout, **kwargs):
    cs = context_string(*args, **kwargs)
    print(cs, file=file)


#################
# evaluate_hint #
#################


def evaluate_hint(typ, ctx=None, lcl=None, typesub=None):
    if isinstance(typ, str):
        if ctx is not None and not isinstance(ctx, dict):
            if isinstance(ctx, (GenericAlias, _GenericAlias)):
                origin = get_origin(ctx)
                if hasattr(origin, "__type_params__"):
                    subs = {p: arg for p, arg in zip(origin.__type_params__, get_args(ctx))}
                    typesub = {**subs, **(typesub or {})}
                ctx = origin
            if hasattr(ctx, "__type_params__"):
                lcl = {p.__name__: p for p in ctx.__type_params__}
            ctx = importlib.import_module(ctx.__module__).__dict__
        return evaluate_hint(eval(typ, ctx, lcl), ctx, lcl, typesub)

    elif isinstance(typ, (UnionType, GenericAlias, _GenericAlias)):
        origin = get_origin(typ)
        args = get_args(typ)
        if origin is UnionType:
            origin = Union
        new_args = [evaluate_hint(arg, ctx, lcl, typesub) for arg in args]
        return origin[tuple(new_args)]

    elif isinstance(typ, TypeVar):
        return typesub.get(typ, typ) if typesub else typ

    elif isinstance(typ, ForwardRef):
        return typ._evaluate(ctx, lcl, type_params=None, recursive_guard=frozenset())

    elif isinstance(typ, type):
        return typ

    else:
        raise TypeError("Cannot evaluate hint:", typ, type(typ))


def _json_type_check(t, bound=object):
    origin = get_origin(t)
    if t is typing.Union:
        return all(_json_type_check(t2) for t2 in get_args(t))
    if not isinstance(origin or t, type) or not issubclass(origin or t, bound):
        return False
    if t in (int, float, str, bool, NoneType):
        return True
    if origin is list:
        (et,) = get_args(t)
        return _json_type_check(et)
    if origin is dict:
        kt, vt = get_args(t)
        return (kt is str) and _json_type_check(vt)
    return False


JSONType = parametrized_class_check(_json_type_check)
