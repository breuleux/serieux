from dataclasses import dataclass, fields
from types import UnionType
from typing import Callable, Union, get_args, get_origin

from ovld import Dataclass, call_next, ovld, recurse

from .utils import UnionAlias, evaluate_hint

MISSING = object()


@dataclass(kw_only=True)
class Field:
    name: str
    type: type
    default: object = MISSING
    default_factory: Callable = MISSING

    argument_name: str | int = MISSING
    property_name: str = MISSING
    serialized_name: str = MISSING

    # Not implemented yet
    flatten: bool = False

    def __post_init__(self):
        if self.property_name is MISSING:
            self.property_name = self.name
        if self.argument_name is MISSING:
            self.argument_name = self.name
        if self.serialized_name is MISSING:
            self.serialized_name = self.name

    @property
    def required(self):
        return self.default is MISSING and self.default_factory is MISSING

    def extract(self, value):
        return getattr(value, self.property_name)

    def extract_codegen(self):
        return f"$$$.{self.property_name}"


class Model(type):
    original_type = object
    fields = []
    constructor = None

    @staticmethod
    def make(
        original_type,
        fields,
        constructor,
    ):
        return Model(
            f"Model[{getattr(original_type, '__name__', str(original_type))}]",
            (Model,),
            {
                "original_type": original_type,
                "fields": fields,
                "constructor": constructor,
            },
        )

    def __class_getitem__(cls, t):
        return model(t)


_model_cache = {}
_premade = {}


def _take_premade(t):
    _model_cache[t] = _premade.pop(t)
    return _model_cache[t]


@ovld(priority=100)
def model(t: type[object]):
    t = evaluate_hint(t)
    if t not in _model_cache:
        _premade[t] = Model.make(
            original_type=t,
            fields=[],
            constructor=None,
        )
        _model_cache[t] = call_next(t)
    return _model_cache[t]


@ovld
def model(dc: type[Dataclass]):
    rval = _take_premade(dc)
    tsub = {}
    constructor = dc
    if (origin := get_origin(dc)) is not None:
        tsub = dict(zip(origin.__type_params__, get_args(dc)))
        constructor = origin

    rval.fields = [
        Field(
            name=field.name,
            type=recurse(evaluate_hint(field.type, ctx=dc, typesub=tsub)),
            default=field.default,
            default_factory=field.default_factory,
            flatten=field.metadata.get("flatten", False),
            argument_name=field.name if field.kw_only else i,
        )
        for i, field in enumerate(fields(constructor))
    ]
    rval.constructor = constructor
    return rval


@ovld
def model(u: type[UnionAlias] | type[UnionType]):
    return Union[tuple(recurse(evaluate_hint(t)) for t in get_args(u))]


@ovld
def model(t: type[object]):
    if (origin := get_origin(t)) is not None:
        return origin[tuple(recurse(evaluate_hint(a)) for a in get_args(t))]
    return t
