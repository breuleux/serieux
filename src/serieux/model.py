import importlib
from dataclasses import dataclass, field
from types import GenericAlias, UnionType
from typing import (
    Callable,
    ForwardRef,
    TypeVar,
    Union,
    _GenericAlias,
    get_args,
    get_origin,
)

from ovld import ovld

#################
# evaluate_hint #
#################


def evaluate_hint(typ, ctx=None, lcl=None, typesub=None):
    if isinstance(typ, str):
        if ctx is not None and not isinstance(ctx, dict):
            if isinstance(ctx, (GenericAlias, _GenericAlias)):
                origin = get_origin(ctx)
                if hasattr(origin, "__type_params__"):
                    subs = {
                        p: arg
                        for p, arg in zip(origin.__type_params__, get_args(ctx))
                    }
                    typesub = {**subs, **(typesub or {})}
                ctx = origin
            if hasattr(ctx, "__type_params__"):
                lcl = {p.__name__: p for p in ctx.__type_params__}
            ctx = importlib.import_module(ctx.__module__).__dict__
        return evaluate_hint(eval(typ, ctx, lcl), ctx, lcl, typesub)

    elif isinstance(typ, (UnionType, GenericAlias, _GenericAlias)):
        origin = get_origin(typ)
        args = get_args(typ)
        if origin is UnionType:
            origin = Union
        new_args = [evaluate_hint(arg, ctx, lcl, typesub) for arg in args]
        return origin[tuple(new_args)]

    elif isinstance(typ, TypeVar):
        return typesub.get(typ, typ) if typesub else typ

    elif isinstance(typ, ForwardRef):
        return typ._evaluate(ctx, lcl, recursive_guard=frozenset())

    elif isinstance(typ, type):
        return typ

    else:
        raise TypeError("Cannot evaluate hint:", typ, type(typ))


###############
# Model types #
###############


@dataclass
class Field:
    name: str = None
    type: object = object
    extractor: Callable = None


@dataclass
class Model:
    original_type: type = field(default=None, kw_only=True)

    def recognizes(self, value):
        return isinstance(value, get_origin(self.original_type))


@dataclass
class StructuredModel(Model):
    builder: Callable
    fields: dict[str, Field]

    def __post_init__(self):
        for k, f in self.fields.items():
            assert f.name is None or f.name == k
            f.name = k

    def fill(self, model):
        for fld in self.fields.values():
            fld.type = model(evaluate_hint(fld.type, self.original_type))


@dataclass
class ListModel(Model):
    builder: Callable
    element_type: type | Model
    extractor: Callable

    def fill(self, model):
        self.element_type = model(
            evaluate_hint(self.element_type, self.original_type)
        )


@dataclass
class MappingModel(Model):
    builder: Callable
    key_type: type | Model
    element_type: type | Model
    extractor: Callable

    def fill(self, model):
        self.key_type = model(evaluate_hint(self.key_type, self.original_type))
        self.element_type = model(
            evaluate_hint(self.element_type, self.original_type)
        )


@dataclass
class UnionModel(Model):
    options: list[type | Model]

    def fill(self, model):
        self.options = [
            model(evaluate_hint(opt, self.original_type))
            for opt in self.options
        ]


##############
# recognizes #
##############


@ovld
def recognizes(model: Model, value):
    return model.recognizes(value)


@ovld
def recognizes(t: type, value):
    return isinstance(value, t)


####################
# Other structures #
####################


@dataclass
class Partial:
    builder: Callable
    args: tuple = None
    kwargs: dict = None

    def __call__(self, *args, **kwargs):
        assert not self.args
        assert not self.kwargs
        return type(self)(self.builder, args, kwargs)


@dataclass
class Multiple:
    parts: list
