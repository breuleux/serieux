from functools import cached_property


class ProxyBase:
    __special_attributes__ = {"_obj", "_computing", "_evaluate", "_type", "__dict__", "_"}

    def __getattribute__(self, name):
        if name in type(self).__special_attributes__:
            return object.__getattribute__(self, name)
        elif name == "__class__":
            return object.__getattribute__(self, "_type") or type(self)
        return getattr(self._obj, name)

    def __setattr__(self, name, value):
        if name in type(self).__special_attributes__:
            return object.__setattr__(self, name, value)
        return setattr(self._obj, name, value)

    def __delattr__(self, name):
        if name in type(self).__special_attributes__:
            return object.__delattr__(self, name)
        return delattr(self._obj, name)

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

    def __setitem__(self, key, value):
        self._obj[key] = value

    def __delitem__(self, key):
        del self._obj[key]

    def __iter__(self):
        return iter(self._obj)

    def __bool__(self):
        return bool(self._obj)

    def __contains__(self, item):
        return item in self._obj

    def __reversed__(self):
        return reversed(self._obj)

    def __index__(self):
        return self._obj.__index__()

    def __enter__(self):
        return self._obj.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._obj.__exit__(exc_type, exc_val, exc_tb)

    def __int__(self):
        return int(self._obj)

    def __float__(self):
        return float(self._obj)

    def __complex__(self):
        return complex(self._obj)

    def __round__(self, ndigits=None):
        return round(self._obj, ndigits) if ndigits is not None else round(self._obj)

    def __trunc__(self):
        return self._obj.__trunc__()

    def __floor__(self):
        return self._obj.__floor__()

    def __ceil__(self):
        return self._obj.__ceil__()

    def __bytes__(self):
        return bytes(self._obj)

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

    def __divmod__(self, other):
        return divmod(self._obj, other)

    def __rdivmod__(self, other):
        return divmod(other, self._obj)

    def __matmul__(self, other):
        return self._obj @ other

    def __rmatmul__(self, other):
        return other @ self._obj

    def __lshift__(self, other):
        return self._obj << other

    def __rshift__(self, other):
        return self._obj >> other

    def __and__(self, other):
        return self._obj & other

    def __or__(self, other):
        return self._obj | other

    def __xor__(self, other):
        return self._obj ^ other

    def __rlshift__(self, other):
        return other << self._obj

    def __rrshift__(self, other):
        return other >> self._obj

    def __rand__(self, other):
        return other & self._obj

    def __ror__(self, other):
        return other | self._obj

    def __rxor__(self, other):
        return other ^ self._obj

    def __invert__(self):
        return ~self._obj

    def __neg__(self):
        return -self._obj

    def __pos__(self):
        return +self._obj

    def __abs__(self):
        return abs(self._obj)

    def __format__(self, fmt):
        return format(self._obj, fmt)

    def __call__(self, *args, **kwargs):
        return self._obj(*args, **kwargs)

    def __copy__(self):
        import copy

        return copy.copy(self._obj)

    def __deepcopy__(self, memo):
        import copy

        return copy.deepcopy(self._obj, memo)


class LazyProxy(ProxyBase):
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
