from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import pairwise
from types import NoneType
from typing import Any, Union, get_args

from ovld import call_next, ovld, recurse

from ..model import Field, FieldModelizable, ListModelizable, Model, StringModelizable, model
from ..tell import Tell, tells as get_tells
from ..utils import UnionAlias
from .tagset import Tagged, TagSet


@dataclass(kw_only=True, frozen=True)
class Step:
    model: Model
    field: Field
    repeat: bool = False

    @property
    def type(self):
        return self.field.type

    @property
    def parent_type(self):
        return self.model.original_type

    def name(self):
        return "#" if self.repeat else self.field.serialized_name


@dataclass(kw_only=True, frozen=True)
class Path:
    steps: list[Step] = field(default_factory=list)

    def follow(self, model, field, repeat=False):
        assert field
        return type(self)(steps=[*self.steps, Step(model=model, field=field, repeat=repeat)])

    @property
    def last(self):
        return self.steps[-1]

    def up(self):
        return Path(steps=self.steps[:-1])

    def __str__(self):
        return ".".join(pn for p in self.steps if (pn := p.name()))


@dataclass(kw_only=True)
class LinearField:
    """A leaf field in the linearized representation."""

    path: Path

    @property
    def field(self):
        return self.path.last.field

    @property
    def type(self):
        return self.path.last.type

    @property
    def identifier(self):
        return str(self.path)


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

    @property
    def group_id(self):
        return str(self.path.up())

    choice_id: int
    expected_value: str = None


@ovld
def linearize(t: type[Any], prefix: str = ""):
    return recurse(
        t,
        None,
        Path(steps=[Step(model=None, field=Field(type=t, serialized_name=prefix))]),
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
def linearize(ft: type[Any @ TagSet], fld: Field | None, path: Path):
    """Field type is directly annotated with a TagSet."""
    results = call_next(ft, fld, path)
    _, ts = TagSet.decompose(ft)
    opts = list(ts.iterate(object))
    if len(opts) == 1:
        tag_fld = Field(type=str, metadata=fld.metadata, serialized_name="$class")
        results.fields.insert(
            0,
            LinearField(path=path.follow(Model(ft), tag_fld)),
        )
        return results
    else:
        return recurse(Union[tuple(Tagged[cls, tag] for tag, cls in opts)], fld, path)


@dataclass(frozen=True)
class LeafTell(Tell):
    pass


@ovld
def linearize(ft: type[UnionAlias], fld: Field | None, path: Path):
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

    group_id = str(path)
    rval = LinearGroup(option_groups={group_id: []})

    groups = [recurse(t, fld, path) for t in options]

    for i, (group, (_, tls)) in enumerate(zip(groups, tells)):
        filter_out = []

        match list(tls):
            case [LeafTell()]:
                (lfld,) = group.fields
                filter_out.append(lfld)
                rval.fields.append(
                    LinearUnlock(
                        choice_id=i,
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
                                    **vars(lfld),
                                )
                            )
                            break

        reduced_fields = [fld for fld in group.fields if fld not in filter_out]
        rval.option_groups[group_id].append(replace(group, fields=reduced_fields))

    return rval


@ovld(priority=1)
def linearize(ft: type[StringModelizable], fld: Field | None, path: Path):
    """StringModelizable is treated as a leaf even if it also has fields."""
    return LinearGroup(fields=[LinearField(path=path)])


@ovld
def linearize(ft: type[FieldModelizable], fld: Field | None, path: Path):
    """Nested struct field → flatten recursively."""
    m = model(ft)
    result = LinearGroup()
    for subfld in m.fields:
        result |= recurse(subfld.type, subfld, path.follow(m, subfld))
    return result


@ovld
def linearize(ft: type[ListModelizable], fld: Field | None, path: Path):
    """List field."""
    m = model(ft)
    ef = m.element_field
    return recurse(ef.type, ef, path.follow(m, ef, True))


@ovld
def linearize(ft: type[Any], fld: Field | None, path: Path):
    """Primitive / leaf field."""
    return LinearGroup(fields=[LinearField(path=path)])
