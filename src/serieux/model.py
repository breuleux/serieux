import re
from dataclasses import MISSING, dataclass, field, fields, is_dataclass, replace
from datetime import date, datetime, timedelta
from functools import cached_property
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Optional,
    TypeAlias,
    get_args,
    get_origin,
)
from zoneinfo import ZoneInfo

from ovld import Dataclass, Lambda, call_next, class_check, ovld, recurse, subclasscheck

from .docstrings import VariableDoc, get_attribute_docstrings
from .exc import ValidationError
from .instructions import Instruction, T, inherit, strip
from .utils import UnionAlias, clsstring, evaluate_hint

UNDEFINED = object()


if TYPE_CHECKING:
    AllowExtras: TypeAlias = Annotated[T, None]
else:
    AllowExtras = Instruction("AllowExtras", annotation_priority=1, inherit=True)


@class_check
def Modelizable(t):
    return isinstance(model(t), Model)


@class_check
def StringModelizable(t):
    return isinstance(m := model(t), Model) and m.from_string is not None


@class_check
def FieldModelizable(t):
    return isinstance(m := model(t), Model) and m.fields is not None


@class_check
def ListModelizable(t):
    return isinstance(m := model(t), Model) and m.element_field is not None


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
    fields: list[Field] = None
    element_field: Field = None
    constructor: Callable = None
    list_constructor: Callable = None
    from_string: Callable = None
    to_string: Callable = None
    regexp: re.Pattern = None
    string_description: str = None
    allow_extras: bool = False

    def __post_init__(self):
        if isinstance(self.regexp, str):
            self.regexp = re.compile(self.regexp)
        if self.element_field is not None and self.list_constructor is None:  # pragma: no cover
            self.list_constructor = self.constructor

    def accepts(self, other):
        ot = strip(self.original_type)
        return subclasscheck(other, get_origin(ot) or ot)

    def is_submodel_of(self, other):
        # TODO: check that the fields are also the same
        return subclasscheck(self.original_type, other.original_type)

    def __str__(self):
        return f"Model({clsstring(self.original_type)})"

    @cached_property
    def property_names(self):
        return {f.property_name for f in self.fields}

    @cached_property
    def constructed_type(self):
        if isinstance(self.constructor, type):
            return self.constructor
        elif self.constructor is None:  # pragma: no cover
            raise TypeError(f"No constructor defined for {self}.")
        else:
            return_type = getattr(self.constructor, "__annotations__", {}).get("return", None)
            if return_type is None:
                raise TypeError(
                    f"Constructor for {self} does not have a return type annotation defined."
                )
            return return_type

    __repr__ = __str__


def constructed_type(t):
    match model(t):
        case None:
            return strip(t)
        case Model() as m:
            return m.constructed_type


_model_cache = {}
_premade = {}


def _take_premade(t):
    _model_cache[t] = _premade.pop(t)
    return _model_cache[t]


#########
# model #
#########


@ovld(priority=100)
def model(t: type[Any]):
    t = evaluate_hint(t)
    if t not in _model_cache:
        _premade[t] = Model(
            original_type=t,
            fields=[],
            constructor=None,
        )
        m = _model_cache[t] = call_next(t)
        if isinstance(cfg := getattr(t, "SerieuxConfig", None), type):
            if (ae := getattr(cfg, "allow_extras", None)) is not None:
                m.allow_extras = ae
    return _model_cache[t]


def safe_isinstance(obj, t):
    try:
        return isinstance(obj, t)
    except TypeError:  # pragma: no cover
        return False


@ovld
def model(dc: type[Dataclass]):
    def make_field(i, field):
        for target in reversed(dc.mro()):
            # Find where the field was defined
            if is_dataclass(target) and field in fields(target):
                break

        typ = evaluate_hint(field.type, target, None, tsub)
        if field.default is None and not safe_isinstance(field.default, typ):
            typ = Optional[typ]

        vardoc = attributes.get(field.name, None) or VariableDoc("", {})
        meta = {**field.metadata, **vardoc.metadata}
        if meta.get("ignore", False):
            return None

        return Field(
            name=field.name,
            description=meta.get("description", None) or vardoc.doc,
            type=typ,
            default=field.default,
            default_factory=field.default_factory,
            flatten=meta.get("flatten", False),
            metavar=meta.get("serieux_metavar", None),
            metadata=meta,
            argument_name=field.name if field.kw_only else i,
        )

    rval = _take_premade(dc)
    tsub = {}
    constructor = dc
    if (origin := get_origin(dc)) is not None:
        tsub = dict(zip(origin.__type_params__, get_args(dc)))
        constructor = origin

    attributes = get_attribute_docstrings(dc)

    _fields = [make_field(i, field) for i, field in enumerate(fields(constructor))]
    rval.fields = [f for f in _fields if f]
    rval.constructor = constructor
    return rval


@ovld
def model(sq: type[list] | type[set] | type[frozenset]):
    (et,) = get_args(sq) or [object]
    return Model(
        original_type=sq,
        element_field=Field(name="*", type=et),
        list_constructor=get_origin(sq) or sq,
    )


@ovld
def model(t: type[Any @ AllowExtras]):
    m = call_next(strip(t, AllowExtras))
    return m and replace(m, allow_extras=True)


@ovld(priority=-1)
def model(t: type[Annotated]):
    if t is Annotated:  # pragma: no cover
        # This is hit in Python <= 3.12
        return None
    m = recurse(strip(t))
    if m and m.fields is not None:
        return Model(
            original_type=m.original_type,
            fields=[replace(field, type=inherit(t, field.type)) for field in m.fields],
            constructor=m.constructor,
        )
    else:
        return m


@ovld
def model(t: type[ZoneInfo]):
    return Model(
        original_type=t,
        from_string=ZoneInfo,
        to_string=Lambda("$obj.key"),
    )


@ovld
def model(t: type[date] | type[datetime]):
    return Model(
        original_type=t,
        from_string=Lambda("$t.fromisoformat($obj)"),
        to_string=Lambda("$t.isoformat($obj)"),
    )


def _timedelta_to_string(obj: timedelta):
    """Serialize timedelta as Xs (seconds) or Xus (microseconds)."""
    seconds = int(obj.total_seconds())
    if obj.microseconds:
        return f"{seconds}{obj.microseconds:06}us"
    else:
        return f"{seconds}s"


def _timedelta_from_string(obj: str):
    """Deserialize a combination of days, hours, etc. as a timedelta."""
    units = {
        "d": "days",
        "h": "hours",
        "m": "minutes",
        "s": "seconds",
        "ms": "milliseconds",
        "us": "microseconds",
    }
    sign = 1
    if obj.startswith("-"):
        obj = obj[1:]
        sign = -1
    kw = {}
    parts = re.split(string=obj, pattern="([a-z ]+)")
    assert parts[-1] == ""
    for i in range(len(parts) // 2):
        n = parts[i * 2]
        unit = parts[i * 2 + 1].strip()
        assert unit in units
        try:
            kw[units[unit]] = float(n)
        except ValueError:
            raise ValidationError(f"Could not convert '{n}' ({units[unit]}) to float")
    return sign * timedelta(**kw)


@ovld
def model(t: type[timedelta]):
    return Model(
        original_type=t,
        from_string=_timedelta_from_string,
        to_string=_timedelta_to_string,
        regexp=r"^[+-]?([\d.]+[dhms]|[\d.]+ms|[\d.]+us)+$",
        string_description="A string such as 1d, 5h or 3d5h7s, ending in a unit. Valid units are d, h, m, s, ms, us.",
    )


@ovld
def model(t: type[re.Pattern]):
    return Model(
        original_type=t,
        from_string=re.compile,
        to_string=Lambda("$obj.pattern"),
    )


@ovld(priority=-1)
def model(t: object):
    return None


############
# field_at #
############


@ovld
def field_at(t: Any, path: Any):
    return field_at(t, path, Field(name="ROOT", type=t))


@ovld
def field_at(t: Any, path: str, f: Field):
    if not path:
        return f
    return recurse(t, path.lstrip(".").split("."), f)


@ovld(priority=10)
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
def field_at(t: type[FieldModelizable], path: list, f: Field):
    m = model(t)
    curr, *rest = path
    for f2 in m.fields:
        if f2.serialized_name == curr:
            return recurse(f2.type, rest, f2)
    return None


@ovld(priority=1)
def field_at(t: type[ListModelizable], path: list, f: Field):
    m = model(t)
    curr, *rest = path
    try:
        int(curr)
    except ValueError:
        return None
    return recurse(m.element_field.type, rest, m.element_field)


@ovld
def field_at(t: type[UnionAlias], path: list, f: Field):
    for opt in get_args(t):
        if (rval := field_at(opt, path, f)) is not None:
            return rval
    return None


@ovld(priority=-1)
def field_at(t: Any, path: list, f: Field):
    return None
