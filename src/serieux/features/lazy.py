from functools import cached_property

from ovld import Medley, call_next, ovld

from ..ctx import Context
from ..typetags import NewTag

#############
# Constants #
#############


Lazy = NewTag["Lazy", 1, False]
DeepLazy = NewTag["DeepLazy", 1]


###########
# Helpers #
###########


class LazyProxy:
    def __init__(self, evaluate):
        self._evaluate = evaluate

    @cached_property
    def _obj(self):
        return self._evaluate()

    def __getattribute__(self, name):
        if name in ("_obj", "_evaluate", "__dict__"):
            return object.__getattribute__(self, name)
        return getattr(self._obj, name)

    def __str__(self):
        return str(self._obj)

    def __repr__(self):
        return repr(self._obj)

    def __eq__(self, other):
        return self._obj == other

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


###################
# Implementations #
###################


class LazyDeserialization(Medley):
    @ovld(priority=1)
    def deserialize(self, typ: type[Lazy], value: object, ctx: Context):
        def evaluate():
            return call_next(typ.pushdown(), value, ctx)

        return LazyProxy(evaluate)

    @ovld(priority=1)
    def deserialize(self, typ: type[DeepLazy], value: object, ctx: Context):
        def evaluate():
            return call_next(typ, value, ctx)

        return LazyProxy(evaluate)
