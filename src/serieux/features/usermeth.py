from dataclasses import replace
from typing import Any

from ovld import Medley, call_next, ovld, recurse
from ovld.types import HasMethod
from ovld.utils import ResolutionError

from ..ctx import Context
from ..model import Model, model
from ..priority import STD4


class UserMethods(Medley):
    @ovld(priority=STD4)
    def deserialize(self, t: type[HasMethod["serieux_deserialize"]], obj: Any, ctx: Context):  # noqa: F821
        def cn(t, obj, ctx, *, from_top=False):
            return recurse(t, obj, ctx) if from_top else call_next(t, obj, ctx)

        try:
            return t.serieux_deserialize(obj, ctx, cn)
        except ResolutionError:
            # If t implements serieux_deserialize with ovld and no method matches, it will
            # throw a ResolutionError and we simply resume our search down the stack.
            return call_next(t, obj, ctx)

    @ovld(priority=STD4)
    def serialize(self, t: type[HasMethod["serieux_serialize"]], obj: Any, ctx: Context):  # noqa: F821
        def cn(t, obj, ctx, *, from_top=False):
            return recurse(t, obj, ctx) if from_top else call_next(t, obj, ctx)

        try:
            return t.serieux_serialize(obj, ctx, cn)
        except ResolutionError:
            return call_next(t, obj, ctx)

    @ovld(priority=STD4)
    def schema(self, t: type[HasMethod["serieux_schema"]], ctx: Context):  # noqa: F821
        def cn(t, ctx, *, from_top=False):
            return recurse(t, ctx) if from_top else call_next(t, ctx)

        try:
            return t.serieux_schema(ctx, cn)
        except ResolutionError:  # pragma: no cover
            return call_next(t, ctx)


@model.register(priority=1)
def _(t: type[HasMethod["serieux_model"]]):  # noqa: F821
    def cn(t, *, from_top=False):  # pragma: no cover
        return recurse(t) if from_top else call_next(t)

    return t.serieux_model(cn)


@model.register(priority=2)
def _(t: type[HasMethod["serieux_to_string"]] | type[HasMethod["serieux_from_string"]]):  # noqa: F821
    m = call_next(t)
    if not m:
        m = Model(t, fields=None)
    if hasattr(t, "serieux_to_string"):
        m = replace(m, to_string=t.serieux_to_string)
    if hasattr(t, "serieux_from_string"):
        m = replace(m, from_string=t.serieux_from_string)
    return m
