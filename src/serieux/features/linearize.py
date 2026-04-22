from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import pairwise
from types import NoneType
from typing import Any, Union, get_args

from ovld import call_next, ovld, recurse

from ..model import Field, FieldModelizable, ListModelizable, Model, StringModelizable, model
from ..tell import Tell, tells as get_tells
from ..utils import UnionAlias
from .tagset import Tagged, TagSet, tag_field


@dataclass(kw_only=True)
class Unlock:
    group: LinearField
    choice_id: int
    expected_value: str | None = None


@dataclass(kw_only=True)
class LinearField:
    """A leaf field in the linearized representation."""

    model: Model
    field: Field
    sequence: bool = False

    parent: LinearField | None = None
    unlock: Unlock | None = None

    def follow(self, model, field, sequence=False):
        assert field
        return type(self)(
            model=model,
            field=field,
            sequence=sequence,
            parent=self,
        )

    @property
    def type(self):
        return self.field.type

    @property
    def enclosing_type(self):
        return self.model.original_type

    @property
    def metadata(self):
        return self.field.metadata

    @property
    def doc(self):
        return self.field.description

    @property
    def enclosing_doc(self):
        return self.model.description

    @property
    def label(self):
        return "#" if self.sequence else self.field.serialized_name

    @property
    def identifier(self):
        pi = self.parent.identifier if self.parent else None
        lbl = self.label
        if pi and lbl:
            return f"{pi}.{lbl}"
        else:
            return pi or lbl or ""


@dataclass(kw_only=True)
class LinearGroup:
    """A group of LinearBase items for one branch of a union, with its associated type."""

    group_field: LinearField = None
    fields: list[LinearField] = field(default_factory=list)
    option_groups: dict[str, list[LinearGroup]] = field(default_factory=dict)

    def __or__(self, other):
        return LinearGroup(
            group_field=self.group_field,
            fields=[*self.fields, *other.fields],
            option_groups={**self.option_groups, **other.option_groups},
        )


@ovld
def linearize(t: type[Any], prefix: str = "", description: str = None):
    if description is None:
        description = getattr(t, "__doc__", None)
    return recurse(
        t,
        LinearField(
            model=None,
            field=Field(type=t, serialized_name=prefix, description=description),
            parent=None,
        ),
    )


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
def linearize(ft: type[Any @ TagSet], fld: LinearField):
    """Field type is directly annotated with a TagSet."""
    results = call_next(ft, fld)
    _, ts = TagSet.decompose(ft)
    opts = list(ts.iterate(object))
    if len(opts) == 1:
        tag_fld = Field(
            type=str,
            metadata=fld.field.metadata,
            serialized_name=tag_field,
            description=model(ft).description,
        )
        results.fields.insert(
            0,
            fld.follow(model=Model(ft), field=tag_fld),
        )
        return results
    else:
        return recurse(Union[tuple(Tagged[cls, tag] for tag, cls in opts)], fld)


@dataclass(frozen=True)
class LeafTell(Tell):
    pass


@ovld
def linearize(ft: type[UnionAlias], fld: LinearField):
    """Field type is a Union — tagged, optional, or plain."""
    options = list(_flatten_options(ft))

    tells = []
    for o in options:
        if (tls := get_tells(o, dict)) is not None:
            tells.append((o, tls))
        elif o is NoneType:
            pass
        else:
            tells.append((o, {LeafTell()}))

    elim = set()
    for (_, tl1), (_, tl2) in pairwise(tells):
        elim |= tl1 & tl2
    for _, tls in tells:
        tls -= elim

    if any(not tls for _, tls in tells):
        raise Exception("Cannot differentiate options")

    group_id = fld.identifier
    rval = LinearGroup(group_field=fld, option_groups={group_id: []})

    groups = [recurse(t, fld) for t in options]

    for i, (group, (_, tls)) in enumerate(zip(groups, tells)):
        filter_out = []
        ul = Unlock(group=fld, choice_id=i)

        match list(tls):
            case [LeafTell()]:
                (lfld,) = group.fields
                filter_out.append(lfld)
                rval.fields.append(replace(lfld, unlock=ul))
            case _:
                for lfld in group.fields:
                    for tl in tls:
                        if tl.key == lfld.field.serialized_name:
                            filter_out.append(lfld)
                            rval.fields.append(
                                replace(
                                    lfld,
                                    unlock=replace(ul, expected_value=getattr(tl, "value", None)),
                                )
                            )
                            break

        reduced_fields = [f for f in group.fields if f not in filter_out]
        rval.option_groups[group_id].append(replace(group, fields=reduced_fields))

    return rval


@ovld(priority=1)
def linearize(ft: type[StringModelizable], fld: LinearField):
    """StringModelizable is treated as a leaf even if it also has fields."""
    return LinearGroup(group_field=fld, fields=[fld])


@ovld
def linearize(ft: type[FieldModelizable], fld: LinearField):
    """Nested struct field → flatten recursively."""
    m = model(ft)
    result = LinearGroup(group_field=fld)
    for subfld in m.fields:
        result |= recurse(subfld.type, fld.follow(model=m, field=subfld))
    return result


@ovld
def linearize(ft: type[ListModelizable], fld: LinearField):
    """List field."""
    m = model(ft)
    ef = m.element_field
    return recurse(ef.type, fld.follow(model=m, field=ef, sequence=True))


@ovld
def linearize(ft: type[Any], fld: LinearField):
    """Primitive / leaf field."""
    return LinearGroup(group_field=fld, fields=[fld])
