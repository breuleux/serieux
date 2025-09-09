from ovld import Exactly, Medley, ovld, recurse

from ..ctx import Context
from ..priority import LO1
from .tagset import ReferencedClass

###################
# Implementations #
###################


class AutoTagAny(Medley):
    @ovld(priority=LO1)
    def serialize(self, t: type[Exactly[object]], obj: object, ctx: Context, /):
        return recurse(t @ ReferencedClass, obj, ctx)

    @ovld(priority=LO1)
    def deserialize(self, t: type[Exactly[object]], obj: dict, ctx: Context, /):
        return recurse(t @ ReferencedClass, obj, ctx)
