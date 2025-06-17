from functools import cached_property
from typing import TYPE_CHECKING, Annotated, Any, TypeAlias

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..instructions import NewInstruction, T
from ..utils import PRIO_HIGHER

#############
# Constants #
#############


if TYPE_CHECKING:
    Lazy: TypeAlias = Annotated[T, None]
    DeepLazy: TypeAlias = Annotated[T, None]
else:
    Lazy = NewInstruction[T, "Lazy", 2, False]
    DeepLazy = NewInstruction[T, "DeepLazy", 2]


###########
# Helpers #
###########


class LazyProxy:
    def __init__(self, evaluate, type=None):
        self._type = type
        self._evaluate = evaluate
        self._computing = False

    @cached_property
    def _obj(self):
        if self._computing:
            raise Exception("Deadlock: asked for a value during its computation.")
        self._computing = True
        try:
            rval = self._evaluate()
            if isinstance(rval, LazyProxy):  # pragma: no cover
                return rval._obj
        finally:
            self._computing = False
        return rval

    def __getattribute__(self, name):
        if name in ("_obj", "_computing", "_evaluate", "_type", "__dict__"):
            return object.__getattribute__(self, name)
        elif name == "__class__":
            return object.__getattribute__(self, "_type") or LazyProxy
        return getattr(self._obj, name)

    def __str__(self):
        return str(self._obj)

    def __repr__(self):
        return repr(self._obj)

    def __eq__(self, other):
        return self._obj == other

    def __ne__(self, other):
        return self._obj != other

    def __lt__(self, other):
        return self._obj < other

    def __le__(self, other):
        return self._obj <= other

    def __gt__(self, other):
        return self._obj > other

    def __ge__(self, other):
        return self._obj >= other

    def __hash__(self):
        return hash(self._obj)

    def __len__(self):
        return len(self._obj)

    def __getitem__(self, key):
        return self._obj[key]

    def __iter__(self):
        return iter(self._obj)

    def __bool__(self):
        return bool(self._obj)

    def __contains__(self, item):
        return item in self._obj

    def __add__(self, other):
        return self._obj + other

    def __sub__(self, other):
        return self._obj - other

    def __mul__(self, other):
        return self._obj * other

    def __truediv__(self, other):
        return self._obj / other

    def __floordiv__(self, other):
        return self._obj // other

    def __mod__(self, other):
        return self._obj % other

    def __pow__(self, other):
        return self._obj**other

    def __radd__(self, other):
        return other + self._obj

    def __rsub__(self, other):
        return other - self._obj

    def __rmul__(self, other):
        return other * self._obj

    def __rtruediv__(self, other):
        return other / self._obj

    def __rfloordiv__(self, other):
        return other // self._obj

    def __rmod__(self, other):
        return other % self._obj

    def __rpow__(self, other):
        return other**self._obj

    def __neg__(self):
        return -self._obj

    def __pos__(self):
        return +self._obj

    def __abs__(self):
        return abs(self._obj)

    def __call__(self, *args, **kwargs):
        return self._obj(*args, **kwargs)


###################
# Implementations #
###################


class LazyDeserialization(Medley):
    @ovld(priority=PRIO_HIGHER - 1)
    def deserialize(self, t: type[Lazy], value: object, ctx: Context):
        def evaluate():
            return recurse(Lazy.strip(t), value, ctx)

        return LazyProxy(evaluate, type=t)

    @ovld(priority=PRIO_HIGHER - 1)
    def deserialize(self, t: type[DeepLazy], value: object, ctx: Context):
        def evaluate():
            return call_next(t, value, ctx)

        return LazyProxy(evaluate, type=t)

    @ovld  # pragma: no cover
    def deserialize(self, t: Any, value: LazyProxy, ctx: Context):
        return recurse(t, value._obj, ctx)


# Add as a default feature in serieux.Serieux
__default_features__ = LazyDeserialization
