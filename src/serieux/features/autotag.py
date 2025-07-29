from ovld import Exactly, Medley, ovld, recurse

from ..ctx import Context
from ..utils import PRIO_LOW
from .tagset import Referenced

###################
# Implementations #
###################


class AutoTagAny(Medley):
    @ovld(priority=PRIO_LOW)
    def serialize(self, t: type[Exactly[object]], obj: object, ctx: Context, /):
        return recurse(t @ Referenced, obj, ctx)

    @ovld(priority=PRIO_LOW)
    def deserialize(self, t: type[Exactly[object]], obj: dict, ctx: Context, /):
        return recurse(t @ Referenced, obj, ctx)
