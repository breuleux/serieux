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

from ovld import class_check, parametrized_class_check

PRIO_LAST = -100
PRIO_LOW = -2
PRIO_DEFAULT = -1
PRIO_HIGH = 1
PRIO_HIGHER = 2
PRIO_TOP = 1000


@class_check
def UnionAlias(cls):
    return get_origin(cls) in (Union, UnionType)


def clsstring(cls):
    cls = getattr(cls, "original_type", cls)
    if args := typing.get_args(cls):
        origin = typing.get_origin(cls) or cls
        args = ", ".join(map(clsstring, args))
        return f"{origin.__name__}[{args}]"
    else:
        r = repr(cls)
        if r.startswith("<class "):
            return cls.__name__
        else:  # pragma: no cover
            return r


#################
# evaluate_hint #
#################


def evaluate_hint(typ, ctx=None, lcl=None, typesub=None):
    def get_eval_args():
        glb = ctx
        tsub = typesub
        local = lcl
        if glb is not None and not isinstance(glb, dict):
            if isinstance(glb, (GenericAlias, _GenericAlias)):
                origin = get_origin(glb)
                if hasattr(origin, "__type_params__"):
                    subs = {p: arg for p, arg in zip(origin.__type_params__, get_args(glb))}
                    tsub = {**subs, **(typesub or {})}
                glb = origin
            if hasattr(glb, "__type_params__"):
                local = {p.__name__: p for p in glb.__type_params__}
            glb = importlib.import_module(glb.__module__).__dict__
        return glb, local, tsub

    if isinstance(typ, str):
        glb, lcl, typesub = get_eval_args()
        return evaluate_hint(eval(typ, glb, lcl), glb, lcl, typesub)

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
        glb, lcl, _ = get_eval_args()
        if sys.version_info >= (3, 13):
            return typ._evaluate(glb, lcl, type_params=None, recursive_guard=frozenset())
        else:  # pragma: no cover
            return typ._evaluate(glb, lcl, recursive_guard=frozenset())

    elif isinstance(typ, type):
        return typ

    else:  # pragma: no cover
        raise TypeError("Cannot evaluate hint:", typ, type(typ))


def _json_type_check(t, bound=object):
    origin = get_origin(t)
    if origin is typing.Union or origin is UnionType:
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
