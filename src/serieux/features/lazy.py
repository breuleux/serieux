from typing import TYPE_CHECKING, Annotated, Any, TypeAlias

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..instructions import Instruction, T, pushdown
from ..priority import HI5
from .proxy import LazyProxy

#############
# Constants #
#############


if TYPE_CHECKING:
    Lazy: TypeAlias = Annotated[T, None]
    DeepLazy: TypeAlias = Annotated[T, None]
else:
    Lazy = Instruction("Lazy", annotation_priority=2, inherit=False)
    DeepLazy = Instruction("DeepLazy", annotation_priority=2, inherit=True)


###################
# Implementations #
###################


class LazyDeserialization(Medley):
    @ovld(priority=HI5)
    def serialize(self, t: Any, value: LazyProxy, ctx: Context):
        return recurse(t, value._obj, ctx)

    @ovld(priority=HI5)
    def deserialize(self, t: type[Any @ Lazy], value: object, ctx: Context):
        def evaluate():
            return recurse(Lazy.strip(t), value, ctx)

        return LazyProxy(evaluate, type=t)

    @ovld(priority=HI5)
    def deserialize(self, t: type[Any @ DeepLazy], value: object, ctx: Context):
        def evaluate():
            return call_next(pushdown(t), value, ctx)

        return LazyProxy(evaluate, type=t)

    @ovld  # pragma: no cover
    def deserialize(self, t: Any, value: LazyProxy, ctx: Context):
        return recurse(t, value._obj, ctx)
