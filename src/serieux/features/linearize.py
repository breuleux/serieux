from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
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


@dataclass(frozen=True)
class Range:
    min: int
    max: int = None


@dataclass(kw_only=True, eq=False)
class LinearField:
    """A leaf field in the linearized representation."""

    model: Model
    field: Field
    sequence: bool = False

    parent: LinearField | None = None
    unlock: list[Unlock] = field(default_factory=list)
    expected_value: str | None = None

    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        self.metadata = dict(self.field.metadata)

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
    def positional(self):
        return self.field.metadata.get("positional", False)

    @property
    def doc(self):
        return self.field.description

    @property
    def enclosing_doc(self):
        return self.model.description

    @property
    def signature(self):
        p = self.parent.signature if self.parent is not None else ()
        return (*p, Range(0, None) if self.sequence else self.field.serialized_name)

    @property
    def identifier(self):
        return ".".join("#" if isinstance(s, Range) else s for s in self.signature if s)

    def __str__(self):
        return f"<LinearField {self.identifier}>"

    __repr__ = __str__


@dataclass(kw_only=True)
class LinearGroup:
    """A group of LinearBase items for one branch of a union, with its associated type."""

    group_field: LinearField = None
    fields: list[LinearField] = field(default_factory=list)
    option_groups: dict[str, list[LinearGroup]] = field(default_factory=dict)

    def __or__(self, other):
        def _push_into_positional_chain(
            subgroup: LinearGroup, other_pos: list, other_pos_ogs: dict
        ) -> LinearGroup:
            """Append other_pos at the terminal end of subgroup's positional chain."""
            current_pos = [f for f in subgroup.fields if f.positional]
            if not current_pos:
                return replace(
                    subgroup,
                    fields=[*subgroup.fields, *other_pos],
                    option_groups={**subgroup.option_groups, **other_pos_ogs},
                )
            pos_og_keys = {ul.group.identifier for f in current_pos for ul in f.unlock}
            if not pos_og_keys:
                # Terminal leaf positionals — the last one gates other_pos.
                last_pos = current_pos[-1]
                ul = Unlock(group=last_pos, choice_id=0)
                updated_last = replace(last_pos, unlock=[*last_pos.unlock, ul])
                new_fields = [updated_last if f is last_pos else f for f in subgroup.fields]
                new_subgroup = LinearGroup(fields=list(other_pos), option_groups=other_pos_ogs)
                return replace(
                    subgroup,
                    fields=new_fields,
                    option_groups={**subgroup.option_groups, last_pos.identifier: [new_subgroup]},
                )
            new_ogs = {
                k: [_push_into_positional_chain(sg, other_pos, other_pos_ogs) for sg in sgs]
                if k in pos_og_keys
                else sgs
                for k, sgs in subgroup.option_groups.items()
            }
            return replace(subgroup, option_groups=new_ogs)

        self_pos = [f for f in self.fields if f.positional]
        other_pos = [f for f in other.fields if f.positional]

        if not self_pos or not other_pos:
            return LinearGroup(
                group_field=self.group_field,
                fields=[*self.fields, *other.fields],
                option_groups={**self.option_groups, **other.option_groups},
            )

        other_pos_og_keys = {ul.group.identifier for f in other_pos for ul in f.unlock}
        other_pos_ogs = {k: v for k, v in other.option_groups.items() if k in other_pos_og_keys}
        other_nonpos_ogs = {
            k: v for k, v in other.option_groups.items() if k not in other_pos_og_keys
        }
        other_nonpos = [f for f in other.fields if not f.positional]

        if self_pos[0].unlock:
            # self's positionals are union triggers — push other_pos into terminal of each branch
            gids = {ul.group.identifier for f in self_pos for ul in f.unlock}
            new_ogs = {
                k: [_push_into_positional_chain(sg, other_pos, other_pos_ogs) for sg in sgs]
                if k in gids
                else sgs
                for k, sgs in self.option_groups.items()
            }
            return LinearGroup(
                group_field=self.group_field,
                fields=[*self.fields, *other_nonpos],
                option_groups={**new_ogs, **other_nonpos_ogs},
            )
        else:
            # self's positionals are leaves — the last one gates other_pos
            last_pos = self_pos[-1]
            ul = Unlock(group=last_pos, choice_id=0)
            updated_last = replace(last_pos, unlock=[*last_pos.unlock, ul])
            new_self_fields = [updated_last if f is last_pos else f for f in self.fields]
            subgroup = LinearGroup(fields=list(other_pos), option_groups=other_pos_ogs)
            return LinearGroup(
                group_field=self.group_field,
                fields=[*new_self_fields, *other_nonpos],
                option_groups={
                    **self.option_groups,
                    last_pos.identifier: [subgroup],
                    **other_nonpos_ogs,
                },
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
            metadata=fld.metadata,
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
                rval.fields.append(replace(lfld, unlock=[*lfld.unlock, ul]))
            case _:
                for lfld in group.fields:
                    if lfld.parent is not fld:
                        continue
                    for tl in tls:
                        if tl.key == lfld.field.serialized_name:
                            filter_out.append(lfld)
                            rval.fields.append(
                                replace(
                                    lfld,
                                    unlock=[*lfld.unlock, ul],
                                    expected_value=getattr(tl, "value", None),
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
    subfld = fld.follow(model=m, field=ef, sequence=True)
    subfld.metadata = fld.metadata
    return recurse(ef.type, subfld)


@ovld
def linearize(ft: type[Any], fld: LinearField):
    """Primitive / leaf field."""
    return LinearGroup(group_field=fld, fields=[fld])


class LinearState(str, Enum):
    AVAILABLE = "AVAILABLE"
    FILLED = "FILLED"
    LATENT = "LATENT"
    UNAVAILABLE = "UNAVAILABLE"
    ADVANCE = "ADVANCE"


@dataclass(kw_only=True)
class FieldState:
    state: LinearState
    note: str | None = None


@ovld
def _flatten(group: LinearGroup, state: str = LinearState.AVAILABLE):
    for field in group.fields:
        yield (field, FieldState(state=state))
    for _, subgroups in group.option_groups.items():
        for subgroup in subgroups:
            yield from recurse(subgroup, LinearState.LATENT)


def _all_subfields(group: LinearGroup):
    yield from group.fields
    for subgroups in group.option_groups.values():
        for subgroup in subgroups:
            yield from _all_subfields(subgroup)


def _sequence_chain(fld: LinearField) -> list[LinearField]:
    """Return sequence fields from fld itself and ancestors, innermost first."""
    chain = []
    p = fld
    while p is not None:
        if p.sequence:
            chain.append(p)
        p = p.parent
    return chain


def _is_descendant_of(fld: LinearField, ancestor: LinearField) -> bool:
    p = fld.parent
    while p is not None:
        if p is ancestor:
            return True
        p = p.parent
    return False


@dataclass
class GroupState:
    initial: LinearGroup
    state: dict[LinearField, FieldState] = None
    _initial_state: dict[LinearField, LinearState] = None
    sequences: dict[LinearField, int] = None

    def __post_init__(self):
        raw = dict(_flatten(self.initial))
        self.state = raw
        self._initial_state = {fld: fs.state for fld, fs in raw.items()}
        self.sequences = {}
        for fld in raw:
            p = fld  # include fld itself in case it is sequence=True
            while p is not None:
                if p.sequence and p not in self.sequences:
                    self.sequences[p] = 0
                p = p.parent
        # Flatten all nested option_groups into one lookup dict keyed by group_id
        self._option_groups: dict[str, list[LinearGroup]] = {}
        self._collect_option_groups(self.initial)

    def _collect_option_groups(self, group: LinearGroup) -> None:
        for k, subgroups in group.option_groups.items():
            self._option_groups[k] = subgroups
            for subgroup in subgroups:
                self._collect_option_groups(subgroup)

    def _concrete_id(self, fld: LinearField) -> str:
        """Return the field identifier with Range placeholders replaced by current indices."""
        seq_iter = iter(reversed(_sequence_chain(fld)))  # outermost first
        parts = []
        for s in fld.signature:
            if isinstance(s, Range):
                parts.append(str(self.sequences[next(seq_iter)]))
            elif s:
                parts.append(s)
        return ".".join(parts)

    def _apply_unlock(self, fld: LinearField, sibling_state: LinearState) -> None:
        for ul in fld.unlock:
            group_id = ul.group.identifier
            choice_id = ul.choice_id

            for other_fld in self.state:
                if other_fld is not fld and any(u.group is ul.group for u in other_fld.unlock):
                    self.state[other_fld] = FieldState(state=sibling_state)

            for i, subgroup in enumerate(self._option_groups.get(group_id, [])):
                if i == choice_id:
                    for sub_fld in subgroup.fields:
                        self.state[sub_fld] = FieldState(state=LinearState.AVAILABLE)
                elif sibling_state == LinearState.UNAVAILABLE:
                    for sub_fld in _all_subfields(subgroup):
                        self.state[sub_fld] = FieldState(state=LinearState.UNAVAILABLE)

    def advance(self, fld: LinearField) -> bool:
        fs = self.state.get(fld)
        if fs is None:
            return False

        chain = _sequence_chain(fld)  # innermost first
        in_sequence = bool(chain)

        if fs.state == LinearState.AVAILABLE:
            # A field is structural (→ ADVANCE) unless an unlock field has already
            # committed the innermost sequence to a specific union branch (→ FILLED).
            is_structural = in_sequence and (
                fld.sequence
                or not any(
                    f is not fld
                    and self.state[f].state in (LinearState.FILLED, LinearState.ADVANCE)
                    and f.unlock
                    and any(u.group is chain[0] for u in f.unlock)
                    for f in self.state
                )
            )
            new_state = LinearState.ADVANCE if is_structural else LinearState.FILLED
            self.state[fld] = FieldState(state=new_state)
            if fld.unlock:
                if new_state == LinearState.ADVANCE:
                    sibling_state = LinearState.ADVANCE
                elif in_sequence:
                    sibling_state = LinearState.AVAILABLE
                else:
                    sibling_state = LinearState.UNAVAILABLE
                self._apply_unlock(fld, sibling_state)
            return self._concrete_id(fld)

        elif fs.state == LinearState.ADVANCE:
            for i, seq in enumerate(chain):  # innermost first
                r = seq.signature[-1]
                assert isinstance(r, Range)
                if r.max is not None and self.sequences[seq] >= r.max - 1:
                    continue
                # Reset inner sequence indices
                for inner in chain[:i]:
                    self.sequences[inner] = 0
                # Advance this sequence
                self.sequences[seq] += 1
                # Reset all descendants to their initial state
                for other_fld in list(self.state):
                    if _is_descendant_of(other_fld, seq):
                        self.state[other_fld] = FieldState(state=self._initial_state[other_fld])
                # Re-apply outer committed unlocks whose effects may have been wiped by the reset
                for f in list(self.state):
                    if (
                        not _is_descendant_of(f, seq)
                        and f.unlock
                        and self.state[f].state in (LinearState.FILLED, LinearState.ADVANCE)
                    ):
                        f_chain = _sequence_chain(f)
                        if self.state[f].state == LinearState.ADVANCE:
                            ss = LinearState.ADVANCE
                        elif f_chain:
                            ss = LinearState.AVAILABLE
                        else:
                            ss = LinearState.UNAVAILABLE
                        self._apply_unlock(f, ss)
                self.state[fld] = FieldState(state=LinearState.ADVANCE)
                if fld.unlock:
                    self._apply_unlock(fld, LinearState.ADVANCE)
                return self._concrete_id(fld)
            return False

        else:
            return False
