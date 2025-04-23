from dataclasses import MISSING, dataclass, field, fields, replace
from typing import Any, Callable, Optional, get_args, get_origin

from ovld import Dataclass, call_next, class_check, ovld, recurse

from .docstrings import get_attribute_docstrings
from .instructions import InstructionType, NewInstruction
from .utils import UnionAlias, clsstring, evaluate_hint

UNDEFINED = object()


Extensible = NewInstruction["Extensible"]


@class_check
def Modelizable(t):
    return isinstance(model(t), Model)


@dataclass(kw_only=True)
class Field:
    name: str
    type: type
    description: str = None
    metadata: dict[str, object] = field(default_factory=dict)
    default: object = UNDEFINED
    default_factory: Callable = UNDEFINED

    argument_name: str | int = UNDEFINED
    property_name: str = UNDEFINED
    serialized_name: str = UNDEFINED

    # Not implemented yet
    flatten: bool = False

    # Meta-variable to store in this field
    metavar: str = None

    def __post_init__(self):
        if self.property_name is UNDEFINED:
            self.property_name = self.name
        if self.argument_name is UNDEFINED:  # pragma: no cover
            self.argument_name = self.name
        if self.serialized_name is UNDEFINED:
            self.serialized_name = self.name
        if self.default is UNDEFINED:  # pragma: no cover
            self.default = MISSING
        if self.default_factory is UNDEFINED:
            self.default_factory = MISSING

    @property
    def required(self):
        return self.default is MISSING and self.default_factory is MISSING


@dataclass
class Model:
    original_type: type
    fields: list[Field]
    constructor: Callable
    extensible: bool = False

    def accepts(self, other):
        ot = self.original_type
        return issubclass(other, get_origin(ot) or ot)

    def is_submodel_of(self, other):
        # TODO: check that the fields are also the same
        return issubclass(self.original_type, other.original_type)

    def __str__(self):
        return f"Model({clsstring(self.original_type)})"

    __repr__ = __str__


_model_cache = {}
_premade = {}


def _take_premade(t):
    _model_cache[t] = _premade.pop(t)
    return _model_cache[t]


@ovld(priority=100)
def model(t: type[object]):
    t = evaluate_hint(t)
    if t not in _model_cache:
        _premade[t] = Model(
            original_type=t,
            fields=[],
            constructor=None,
        )
        _model_cache[t] = call_next(t)
    return _model_cache[t]


@ovld
def model(dc: type[Dataclass]):
    def make_field(i, field):
        typ = evaluate_hint(field.type, dc, None, tsub)
        if field.default is None and not isinstance(field.default, typ):
            typ = Optional[typ]

        return Field(
            name=field.name,
            description=(
                (meta := field.metadata).get("description", None)
                or attributes.get(field.name, None)
            ),
            type=typ,
            default=field.default,
            default_factory=field.default_factory,
            flatten=meta.get("flatten", False),
            metavar=meta.get("serieux_metavar", None),
            metadata=dict(meta),
            argument_name=field.name if field.kw_only else i,
        )

    rval = _take_premade(dc)
    tsub = {}
    constructor = dc
    if (origin := get_origin(dc)) is not None:
        tsub = dict(zip(origin.__type_params__, get_args(dc)))
        constructor = origin

    attributes = get_attribute_docstrings(dc)

    rval.fields = [make_field(i, field) for i, field in enumerate(fields(constructor))]
    rval.constructor = constructor
    return rval


@ovld
def model(t: type[Extensible]):
    m = call_next(t.strip(t))
    return replace(m, extensible=True)


@ovld(priority=-1)
def model(t: type[InstructionType]):
    m = call_next(t.strip(t))
    if m:
        return Model(
            original_type=m.original_type,
            fields=[replace(field, type=t[field.type]) for field in m.fields],
            constructor=m.constructor,
        )


@ovld(priority=-1)
def model(t: object):
    return None


@ovld
def field_at(t: Any, path: Any):
    return field_at(t, path, Field(name="ROOT", type=t))


@ovld
def field_at(t: Any, path: str, f: Field):
    if not path:
        return f
    return recurse(t, path.split("."), f)


@ovld(priority=1)
def field_at(t: Any, path: list, f: Field):
    if not path:
        return f
    else:
        return call_next(t, path, f)


@ovld
def field_at(t: type[dict], path: list, f: Field):
    (_, et) = get_args(t) or (str, object)
    _, *rest = path
    return recurse(et, rest, Field(name=f.name, type=et))


@ovld
def field_at(t: type[Modelizable], path: list, f: Field):
    m = model(t)
    curr, *rest = path
    for f2 in m.fields:
        if f2.serialized_name == curr:
            return recurse(f2.type, rest, f2)
    return None


@ovld
def field_at(t: type[UnionAlias], path: list, f: Field):
    for opt in get_args(t):
        if (rval := field_at(opt, path, f)) is not None:
            return rval
    return None


@ovld(priority=-1)
def field_at(t: Any, path: list, f: Field):
    return None
