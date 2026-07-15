import inspect
from dataclasses import replace
from typing import Any, get_args, get_origin, get_type_hints

from ovld import Medley, call_next, ovld, recurse
from ovld.types import HasMethod
from ovld.utils import ResolutionError

from ..ctx import Context
from ..model import Field, Model, model
from ..priority import STD4

PRIO = STD4.next()


class UserMethods(Medley):
    @ovld(priority=PRIO)
    def deserialize(self, t: type[HasMethod["serieux_deserialize"]], obj: Any, ctx: Context):  # noqa: F821
        def cn(t, obj, ctx, *, from_top=False):
            return recurse(t, obj, ctx) if from_top else call_next(t, obj, ctx)

        cn.serieux = self

        try:
            # NOTE: we want to preserve the type arguments, but if f is a classmethod,
            # C[T].f == C.f, which will receive C as its first argument. Here we simply
            # make sure that f will indeed receive C[T].
            return t.serieux_deserialize.__func__(t, obj, ctx, cn)
        except ResolutionError:
            # If t implements serieux_deserialize with ovld and no method matches, it will
            # throw a ResolutionError and we simply resume our search down the stack.
            return call_next(t, obj, ctx)

    @ovld(priority=PRIO)
    def serialize(self, t: type[HasMethod["serieux_serialize"]], obj: Any, ctx: Context):  # noqa: F821
        def cn(t, obj, ctx, *, from_top=False):
            return recurse(t, obj, ctx) if from_top else call_next(t, obj, ctx)

        cn.serieux = self

        try:
            return t.serieux_serialize.__func__(t, obj, ctx, cn)
        except ResolutionError:
            return call_next(t, obj, ctx)

    @ovld(priority=PRIO)
    def schema(self, t: type[HasMethod["serieux_schema"]], ctx: Context):  # noqa: F821
        def cn(t, ctx, *, from_top=False):
            return recurse(t, ctx) if from_top else call_next(t, ctx)

        cn.serieux = self

        try:
            return t.serieux_schema.__func__(t, ctx, cn)
        except ResolutionError:  # pragma: no cover
            return call_next(t, ctx)


@model.register(priority=1)
def _(t: type[HasMethod["serieux_model"]]):  # noqa: F821
    def cn(t, *, from_top=False):  # pragma: no cover
        return recurse(t) if from_top else call_next(t)

    return t.serieux_model(cn)


@model.register(priority=2)
def _(
    t: type[HasMethod["serieux_to_string"]]  # noqa: F821
    | type[HasMethod["serieux_from_string"]]  # noqa: F821
    | type[HasMethod["serieux_to_number"]]  # noqa: F821
    | type[HasMethod["serieux_from_number"]]  # noqa: F821
    | type[HasMethod["serieux_to_list"]]  # noqa: F821
    | type[HasMethod["serieux_from_list"]]  # noqa: F821
    | type[HasMethod["serieux_to_dict"]]  # noqa: F821
    | type[HasMethod["serieux_from_dict"]],  # noqa: F821
):
    m = call_next(t)
    if not m:
        m = Model(t, fields=None)
    if hasattr(t, "serieux_to_string"):
        m = replace(m, to_string=t.serieux_to_string)
    if hasattr(t, "serieux_from_string"):
        m = replace(m, from_string=t.serieux_from_string)
    if hasattr(t, "serieux_to_number"):
        m = replace(m, to_number=t.serieux_to_number)
    if hasattr(t, "serieux_from_number"):
        m = replace(m, from_number=t.serieux_from_number)
    if hasattr(t, "serieux_from_list"):
        fn = t.serieux_from_list
        (param_name, *_) = inspect.signature(fn).parameters
        hints = get_type_hints(fn)
        ann = hints.get(param_name)
        if get_origin(ann) is not list:
            raise TypeError(
                f"{t}.serieux_from_list's first argument must be annotated as list[T],"
                f" where T is the element type, but it is annotated as {ann!r}"
            )
        (element_type,) = get_args(ann)
        m = replace(m, from_list=fn, element_field=Field(type=element_type))
    if hasattr(t, "serieux_to_list"):
        m = replace(m, to_list=t.serieux_to_list)
    if hasattr(t, "serieux_from_dict"):
        fn = t.serieux_from_dict
        (param_name, *_) = inspect.signature(fn).parameters
        hints = get_type_hints(fn)
        ann = hints.get(param_name)
        if get_origin(ann) is not dict:
            raise TypeError(
                f"{t}.serieux_from_dict's first argument must be annotated as dict[str, T],"
                f" where T is the value type, but it is annotated as {ann!r}"
            )
        (key_type, value_type) = get_args(ann)
        if key_type is not str:
            raise TypeError(
                f"{t}.serieux_from_dict's first argument must be annotated as dict[str, T],"
                f" but its key type is {key_type!r}, not str"
            )
        m = replace(m, from_dict=fn, element_field=Field(type=value_type))
    if hasattr(t, "serieux_to_dict"):
        m = replace(m, to_dict=t.serieux_to_dict)
    return m
