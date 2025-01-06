from dataclasses import dataclass
from functools import cache
from typing import get_args, get_origin

from ovld import subclasscheck
from ovld.mro import Order


@dataclass(frozen=True)
class Tag:
    name: str
    priority: int


def make_tag(name, priority):
    tag = Tag(name=name, priority=priority)
    return _create(frozenset({tag}), object)


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
        typ = self.strip(self)
        if orig := get_origin(typ):
            args = get_args(typ)
            return orig[tuple([self[a] for a in args])]
        else:
            return typ
