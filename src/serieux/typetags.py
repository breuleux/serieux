from dataclasses import dataclass, replace
from functools import cache
from types import UnionType
from typing import Union, get_args, get_origin

from ovld import recurse, subclasscheck
from ovld.mro import Order

from .model import Model, model


@dataclass(frozen=True)
class Tag:
    name: str
    priority: int
    inherit: bool = True


def make_tag(name, priority=1, inherit=True) -> type:
    tag = Tag(name=name, priority=priority, inherit=inherit)
    return _create(frozenset({tag}), object)


class NewTag:
    def __class_getitem__(cls, params) -> type:
        if not isinstance(params, tuple):
            params = (params,)
        return make_tag(*params)


@cache
def _create(tags, cls):
    if isinstance(cls, type) and issubclass(cls, TaggedType):
        return _create(tags | cls._tags, cls._cls)
    if not tags:
        return cls
    else:
        name = "&".join(t.name for t in tags)
        clsname = getattr(cls, "__name__", str(cls))
        return type(f"{name}[{clsname}]", (TaggedType,), {"_tags": tags, "_cls": cls})


class TaggedType(type):
    _cls = object
    _tags = frozenset()

    @classmethod
    def __is_supertype__(self, other):
        return (
            isinstance(other, type)
            and issubclass(other, TaggedType)
            and other._tags.issuperset(self._tags)
            and subclasscheck(other._cls, self._cls)
        )

    @classmethod
    def __type_order__(self, other):
        if not (isinstance(other, type) and issubclass(other, TaggedType)):
            return NotImplemented
        prio = tuple(sorted(tag.priority for tag in self._tags))
        prio_o = tuple(sorted(tag.priority for tag in other._tags))
        return Order.LESS if prio > prio_o else Order.MORE if prio < prio_o else Order.NONE

    def __class_getitem__(self, t):
        return _create(self._tags, t)

    @classmethod
    def strip(cls, t):
        if isinstance(t, type) and issubclass(t, TaggedType):
            return _create(t._tags - cls._tags, t._cls)
        return t

    @classmethod
    def pushdown(self):
        return pushdown(self)


def pushdown(cls):
    if not isinstance(cls, type) or not issubclass(cls, TaggedType):
        return cls
    typ = cls.strip(cls)
    cls = _create(cls._tags - {tag for tag in cls._tags if not tag.inherit}, cls._cls)
    if not isinstance(cls, type) or not issubclass(cls, TaggedType):
        return cls
    if isinstance(typ, type) and issubclass(typ, Model):
        return Model.make(
            original_type=typ.original_type,
            fields=[replace(field, type=cls[field.type]) for field in typ.fields],
            constructor=typ.constructor,
        )
    elif orig := get_origin(typ):
        args = get_args(typ)
        if orig is UnionType:
            orig = Union
        return orig[tuple([cls[a] for a in args])]
    else:
        return typ


def strip_all(cls):
    if isinstance(cls, type) and issubclass(cls, TaggedType):
        return cls.strip(cls)
    return cls


@model.register
def model(t: type[TaggedType]):
    return t[recurse(t._cls)]
