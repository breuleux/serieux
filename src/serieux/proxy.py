import inspect
from dataclasses import dataclass, field, replace

from wrapt import ObjectProxy

proxy_cache = {}


class Proxy(ObjectProxy):

    @classmethod
    def make(cls, obj, ann):
        return cls[type(obj)](obj, ann)

    @classmethod
    def newclass(cls, typ, members={}):
        proxy_cache[cls, typ] = type(
            f"{cls.__name__}[{typ.__qualname__}]",
            (cls,),
            {
                "_self_basis": cls,
                "__proxy_for__": typ,
                **members,
            },
        )
        return proxy_cache[cls, typ]

    def __class_getitem__(thiscls, cls):
        if (thiscls, cls) not in proxy_cache:
            return thiscls.newclass(cls)
        else:
            return proxy_cache[thiscls, cls]

    def __init__(self, wrapped, annotations):
        super().__init__(wrapped)
        self._self_ann = annotations

    def __getitem__(self, item):
        if isinstance(item, type) and issubclass(item, ProxyAnnotation):
            return self._self_ann.get(item)
        else:
            return self.__wrapped__[item]

    def __repr__(self):
        return repr(self.__wrapped__)


####################
# Annotation types #
####################


class ProxyAnnotation:
    pass


class AccessorPart:
    pass


@dataclass
class Item(AccessorPart):
    item: object

    def __str__(self):
        return f"[{self.item!r}]"


@dataclass
class Attribute(AccessorPart):
    attr: str

    def __str__(self):
        return f".{self.attr}"


@dataclass
class Accessor(ProxyAnnotation):
    root: object
    path: list[AccessorPart] = field(default_factory=list)

    def __str__(self):
        return "".join(map(str, self.path))


def get_annotations(prox):
    return getattr(prox, "_self_ann", {})


#################
# TrackingProxy #
#################


class TrackingProxy(Proxy):
    @classmethod
    def make(cls, obj, ann=None):
        ann = ann or {}
        if Accessor not in ann:
            ann[Accessor] = Accessor(root=obj, path=[])
        (_, obj, ann) = _extract(obj, ann)
        basis = getattr(cls, "_self_basis", None) or cls
        return basis[type(obj)](obj, ann)

    def _wrap(self, x, path_part):
        pathed = self._self_ann[Accessor]
        path = [*pathed.path, path_part]
        return type(self).make(x, {Accessor: replace(pathed, path=path)})

    def __getitem__(self, item):
        if isinstance(item, type) and issubclass(item, ProxyAnnotation):
            return self._self_ann.get(item)
        return self._wrap(self.__wrapped__[item], Item(item))

    def __getattr__(self, attr):
        rval = getattr(self.__wrapped__, attr)
        if inspect.ismethod(rval):
            return rval
        return self._wrap(rval, Attribute(attr))

    def __iter__(self):
        for i, x in enumerate(self.__wrapped__):
            yield self._wrap(x, Item(i))


_basic_class_members = list(vars(type("_dummy", (), {})).keys())


def _specialize_TrackingProxy(type):
    def deco(cls):
        members = {
            k: v for k, v in vars(cls).items() if k not in _basic_class_members
        }
        return TrackingProxy.newclass(type, members)

    return deco


@_specialize_TrackingProxy(dict)
class _tp_dict:
    def items(self):
        yield from (
            (k, self._wrap(v, Item(k))) for k, v in self.__wrapped__.items()
        )

    def values(self):
        yield from (self._wrap(v, Item(k)) for k, v in self.__wrapped__.items())

    def get(self, key, default=None):
        return self._wrap(self.__wrapped__.get(key, default), Item(key))


def _extract(x, ann):
    if isinstance(x, Proxy):
        ann = {**x._self_ann, **ann}
        return (type(x), x.__wrapped__, ann)
    else:
        return (None, x, ann)


def proxy(x, ann, typ=None):
    (typ2, x, ann) = _extract(x, ann)
    typ = typ or typ2 or Proxy
    return typ.make(x, ann)
