from typing import Any

from ovld import Medley, call_next, ovld, recurse
from ovld.types import HasMethod
from ovld.utils import ResolutionError

from ..ctx import Context
from ..model import model
from ..utils import PRIO_DEFAULT


class UserMethods(Medley):
    @ovld(priority=PRIO_DEFAULT + 0.5)
    def deserialize(self, t: type[HasMethod["serieux_deserialize"]], obj: Any, ctx: Context):  # noqa: F821
        def cn(t, obj, ctx, *, from_top=False):
            return recurse(t, obj, ctx) if from_top else call_next(t, obj, ctx)

        try:
            return t.serieux_deserialize(obj, ctx, cn)
        except ResolutionError:
            return call_next(t, obj, ctx)

    @ovld(priority=PRIO_DEFAULT + 0.5)
    def serialize(self, t: type[HasMethod["serieux_serialize"]], obj: Any, ctx: Context):  # noqa: F821
        def cn(t, obj, ctx, *, from_top=False):
            return recurse(t, obj, ctx) if from_top else call_next(t, obj, ctx)

        try:
            return t.serieux_serialize(obj, ctx, cn)
        except ResolutionError:
            return call_next(t, obj, ctx)

    @ovld(priority=PRIO_DEFAULT + 0.5)
    def schema(self, t: type[HasMethod["serieux_schema"]], ctx: Context):  # noqa: F821
        def cn(t, ctx, *, from_top=False):
            return recurse(t, ctx) if from_top else call_next(t, ctx)

        try:
            return t.serieux_schema(ctx, cn)
        except ResolutionError:  # pragma: no cover
            # ovld isn't very useful for schema, outside of argument `t`,
            # which is given.
            return call_next(t, ctx)


@model.register(priority=1)
def _(t: type[HasMethod["serieux_model"]]):  # noqa: F821
    def cn(t, *, from_top=False):  # pragma: no cover
        return recurse(t) if from_top else call_next(t)

    return t.serieux_model(cn)


# Add as a default feature in serieux.Serieux
__default_features__ = UserMethods
