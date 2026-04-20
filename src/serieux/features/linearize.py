from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import pairwise
from types import NoneType
from typing import Any, Union, get_args
from uuid import uuid4

from ovld import call_next, ovld, recurse

from ..model import Field, FieldModelizable, StringModelizable, model
from ..tell import Tell, tells as get_tells
from ..utils import UnionAlias
from .tagset import Tagged, TagSet


def _subpath(p, field):
    return f"{p}.{field}" if p else field


@dataclass(kw_only=True)
class LinearBase:
    field: Field
    path: str


@dataclass(kw_only=True)
class LinearField(LinearBase):
    """A leaf field in the linearized representation."""

    type: type


@dataclass(kw_only=True)
class LinearGroup:
    """A group of LinearBase items for one branch of a union, with its associated type."""

    fields: list[LinearField] = field(default_factory=list)
    option_groups: dict[str, list[LinearGroup]] = field(default_factory=dict)

    def __or__(self, other):
        return LinearGroup(
            fields=[*self.fields, *other.fields],
            option_groups={**self.option_groups, **other.option_groups},
        )


@dataclass(kw_only=True)
class LinearUnlock(LinearField):
    """A branch point in the linearized representation."""

    group_id: str
    choice_id: int
    expected_value: str = None


@ovld
def linearize(t: type[Any], prefix: str = ""):
    return recurse(t, None, prefix)


@ovld
def _flatten_options(ft: type[Any @ TagSet]):
    _, ts = TagSet.decompose(ft)
    for tag, cls in ts.iterate(object):
        yield Tagged[cls, tag]


@ovld
def _flatten_options(ft: type[UnionAlias]):
    for opt in get_args(ft):
        yield from recurse(opt)


@ovld
def _flatten_options(ft: type[Any]):
    yield ft


@ovld(priority=1)
def linearize(ft: type[Any @ TagSet], fld: Field | None, path: str):
    """Field type is directly annotated with a TagSet."""
    results = call_next(ft, fld, path)
    _, ts = TagSet.decompose(ft)
    opts = list(ts.iterate(object))
    if len(opts) == 1:
        results.fields.insert(
            0,
            LinearField(
                type=str,
                field=Field(type=str, serialized_name="$class"),
                path=_subpath(path, "$class"),
            ),
        )
        return results
    else:
        return recurse(Union[tuple(Tagged[cls, tag] for tag, cls in opts)], fld, path)


@dataclass(frozen=True)
class LeafTell(Tell):
    pass


@dataclass(frozen=True)
class AbsentTell(Tell):
    pass


@ovld
def linearize(ft: type[UnionAlias], fld: Field | None, path: str):
    """Field type is a Union — tagged, optional, or plain."""
    options = list(_flatten_options(ft))

    tells = []
    for o in options:
        if (tls := get_tells(o, dict)) is not None:
            tells.append((o, tls))
        elif o is NoneType:
            tells.append((o, {AbsentTell()}))
        else:
            tells.append((o, {LeafTell()}))

    elim = set()
    for (_, tl1), (_, tl2) in pairwise(tells):
        elim |= tl1 & tl2
    for _, tls in tells:
        tls -= elim

    if any(not tls for _, tls in tells):
        raise Exception("Cannot differentiate options")

    group_id = uuid4().hex
    rval = LinearGroup(option_groups={group_id: []})

    groups = [recurse(t, fld, path) for t in options]

    for i, (group, (_, tls)) in enumerate(zip(groups, tells)):
        filter_out = []

        match list(tls):
            case [LeafTell() | AbsentTell()]:
                (lfld,) = group.fields
                filter_out.append(lfld)
                rval.fields.append(
                    LinearUnlock(
                        choice_id=i,
                        group_id=group_id,
                        **vars(lfld),
                    )
                )
            case _:
                for lfld in group.fields:
                    for tl in tls:
                        if tl.key == lfld.field.serialized_name:
                            filter_out.append(lfld)
                            rval.fields.append(
                                LinearUnlock(
                                    choice_id=i,
                                    expected_value=getattr(tl, "value", None),
                                    group_id=group_id,
                                    **vars(lfld),
                                )
                            )
                            break

        reduced_fields = [fld for fld in group.fields if fld not in filter_out]
        rval.option_groups[group_id].append(replace(group, fields=reduced_fields))

    return rval


@ovld(priority=1)
def linearize(ft: type[StringModelizable], fld: Field | None, path: str):
    """StringModelizable is treated as a leaf even if it also has fields."""
    return LinearGroup(
        fields=[LinearField(type=ft, field=fld, path=path)],
    )


@ovld
def linearize(ft: type[FieldModelizable], fld: Field | None, path: str):
    """Nested struct field → flatten recursively."""
    m = model(ft)
    result = LinearGroup()
    for subfld in m.fields:
        result |= recurse(subfld.type, subfld, _subpath(path, subfld.name))
    return result


@ovld
def linearize(ft: type[Any], fld: Field | None, path: str):
    """Primitive / leaf field."""
    return LinearGroup(
        fields=[LinearField(type=ft, field=fld, path=path)],
    )
