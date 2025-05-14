import importlib
import inspect
import sys
import typing
from types import GenericAlias, NoneType, UnionType
from typing import (
    Annotated,
    ForwardRef,
    Literal,
    TypeVar,
    Union,
    _GenericAlias,
    get_args,
    get_origin,
)

from ovld import class_check, parametrized_class_check

from .instructions import strip_all

try:
    from typing import TypeAliasType
except ImportError:  # pragma: no cover
    # It won't occur anyway
    class TypeAliasType:
        pass


PRIO_LAST = -100
PRIO_LOW = -2
PRIO_DEFAULT = -1
PRIO_HIGH = 10
PRIO_HIGHER = 20
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


def basic_type(t):
    return get_origin(bt := strip_all(t)) or bt


#################
# evaluate_hint #
#################


class Indirect:
    def __init__(self, value):
        self.__value__ = value


def evaluate_hint(typ, ctx=None, lcl=None, typesub=None, seen=None):
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
        if seen and (typ in seen):
            if seen[typ] is None:
                seen[typ] = Indirect(None)
            return seen[typ]
        else:
            glb, lcl, typesub = get_eval_args()
            if not seen:
                seen = {}
            seen[typ] = None
            rval = evaluate_hint(eval(typ, glb, lcl), glb, lcl, typesub, seen)
            if seen[typ] is not None:
                seen[typ].__value__ = rval
            return rval

    elif isinstance(typ, (UnionType, GenericAlias, _GenericAlias)):
        origin = get_origin(typ)
        if origin is Literal:
            return typ
        args = get_args(typ)
        if origin is Annotated:  # pragma: no cover
            return args[0]
        if origin is UnionType:
            origin = Union
        new_args = [evaluate_hint(arg, ctx, lcl, typesub, seen) for arg in args]
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

    elif isinstance(typ, (Indirect, TypeAliasType)):
        return typ.__value__

    else:  # pragma: no cover
        raise TypeError("Cannot evaluate hint:", typ, type(typ))


####################
# Other type stuff #
####################


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


JSON = parametrized_class_check(_json_type_check)


@class_check
def IsLiteral(t):
    return get_origin(t) is Literal


########
# Misc #
########


def check_signature(fn, flavor, expected):
    params = list(inspect.signature(fn).parameters.keys())
    nexpected = len(expected)
    expected = ", ".join(expected)
    if params[0] != "self" or len(params) != nexpected:  # pragma: no cover
        raise TypeError(
            f"{flavor} '{fn}' must define {nexpected} arguments: ({expected}). The first argument *must* be named 'self'."
        )
