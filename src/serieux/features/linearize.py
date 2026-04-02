from __future__ import annotations

from dataclasses import dataclass
from types import NoneType
from typing import Any, get_args

from ovld import ovld, recurse

from ..model import Field, FieldModelizable, StringModelizable, model
from ..utils import UnionAlias
from .tagset import TagSet, decompose


@dataclass(kw_only=True)
class LinearBase:
    owner: type
    field: Field
    path: str


@dataclass(kw_only=True)
class LinearField(LinearBase):
    """A leaf field in the linearized representation."""

    type: type


@dataclass
class LinearGroup:
    """A group of LinearBase items for one branch of a tagged union, with its associated type."""

    type: type
    items: list[LinearBase]


@dataclass(kw_only=True)
class LinearTagged(LinearBase):
    """A tagged-union branch point in the linearized representation."""

    options: dict[str, LinearGroup]


@dataclass(kw_only=True)
class LinearChoice(LinearBase):
    """A plain (untagged) Union branch point in the linearized representation."""

    options: list[list[LinearBase]]


# Two-argument form: linearize all fields of a struct type
@ovld
def linearize(t: type[FieldModelizable], prefix: str = ""):
    """Flatten a struct type into a list of LinearField / LinearChoice."""
    m = model(t)
    result = []
    for fld in m.fields:
        if fld.name.startswith("_"):  # pragma: no cover
            continue
        path = f"{prefix}.{fld.name}" if prefix else fld.name
        result.extend(recurse(fld.type, t, fld, path))
    return result


# Four-argument form: decide what a single field contributes


@ovld(priority=1)
def linearize(ft: type[Any @ TagSet], owner: type, fld: Field, path: str):
    """Field type is directly annotated with a TagSet."""
    base, ts = decompose(ft)
    options = {
        tag: LinearGroup(type=cls, items=recurse(cls, path)) for tag, cls in ts.iterate(base)
    }
    return [LinearTagged(owner=owner, field=fld, path=path, options=options)]


@ovld
def linearize(ft: type[UnionAlias], owner: type, fld: Field, path: str):
    """Field type is a Union — tagged, optional, or plain."""
    non_none = [a for a in get_args(ft) if a is not NoneType]
    tagged = [a for a in non_none if TagSet.extract(a)]

    # All non-None arms are tagged → LinearTagged
    if tagged and len(tagged) == len(non_none):
        options = {}
        for arg in tagged:
            base, ts = decompose(arg)
            for tag, cls in ts.iterate(base):
                options[tag] = LinearGroup(type=cls, items=recurse(cls, path))
        return [LinearTagged(owner=owner, field=fld, path=path, options=options)]

    # Optional[T] with a single non-None member
    if len(non_none) == 1:
        inner = non_none[0]
        # Pure struct (not string-serializable) → flatten transparently
        if issubclass(inner, FieldModelizable) and not issubclass(inner, StringModelizable):
            return recurse(inner, path)
        # Leaf (StringModelizable, primitive, etc.) → dispatch through 4-arg form
        return recurse(inner, owner, fld, path)

    # Plain union → LinearChoice, one list per member
    options = [recurse(a, owner, fld, path) for a in non_none]
    return [LinearChoice(owner=owner, field=fld, path=path, options=options)]


@ovld(priority=1)
def linearize(ft: type[StringModelizable], owner: type, fld: Field, path: str):
    """StringModelizable is treated as a leaf even if it also has fields."""
    return [LinearField(type=ft, owner=owner, field=fld, path=path)]


@ovld
def linearize(ft: type[FieldModelizable], owner: type, fld: Field, path: str):
    """Nested struct field → flatten recursively."""
    return recurse(ft, path)


@ovld
def linearize(ft: type[Any], owner: type, fld: Field, path: str):
    """Primitive / leaf field."""
    return [LinearField(type=ft, owner=owner, field=fld, path=path)]
