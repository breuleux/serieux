import importlib
from dataclasses import dataclass, field
from types import UnionType
from typing import Any, Callable, Union, _GenericAlias, _UnionGenericAlias

from ovld import call_next, ovld, recurse

################
# canonicalize #
################


@ovld
def canonicalize(t: object):  # noqa: F811
    return recurse(t, __builtins__, {})


@ovld
def canonicalize(t: Any, ctx: object, typesub=None):  # noqa: F811
    if isinstance(ctx, _GenericAlias):
        origin = ctx.__origin__
        params = getattr(origin, "__type_params__", ())
        args = ctx.__args__
        return recurse(
            t, origin, {tv.__name__: value for tv, value in zip(params, args)}
        )
    else:
        if hasattr(ctx, "__module__"):
            glb = importlib.import_module(ctx.__module__).__dict__
            typesub = typesub or {
                p.__name__: p for p in getattr(ctx, "__type_params__", ())
            }
        else:
            glb = typesub = {}
        return recurse(t, glb, typesub)


@ovld
def canonicalize(t: UnionType, ctx: dict, typesub):  # noqa: F811
    return Union[tuple(recurse(t2, ctx, typesub) for t2 in t.__args__)]


@ovld
def canonicalize(t: str, ctx: dict, typesub):  # noqa: F811
    evaluated = eval(t, ctx, typesub)
    return call_next(evaluated, ctx, typesub)


@ovld
def canonicalize(t: type, ctx: dict, typesub):  # noqa: F811
    if isinstance(t, _UnionGenericAlias):
        return Union[tuple(recurse(t2, ctx, typesub) for t2 in t.__args__)]
    else:
        return t


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


@dataclass
class StructuredModel(Model):
    builder: Callable
    fields: dict[str, Field]

    def __post_init__(self):
        for k, f in self.fields.items():
            assert f.name is None or f.name == k
            f.name = k

    def fill(self, model):
        for field in self.fields.values():
            field.type = model(canonicalize(field.type, self.original_type))


@dataclass
class ListModel(Model):
    builder: Callable
    element_type: type | Model
    extractor: Callable

    def fill(self, model):
        self.element_type = model(
            canonicalize(self.element_type, self.original_type)
        )


@dataclass
class MappingModel(Model):
    builder: Callable
    key_type: type | Model
    element_type: type | Model
    extractor: Callable

    def fill(self, model):
        self.key_type = model(canonicalize(self.key_type, self.original_type))
        self.element_type = model(
            canonicalize(self.element_type, self.original_type)
        )


@dataclass
class UnionModel(Model):
    options: list[type | Model]

    def fill(self, model):
        self.options = [
            model(canonicalize(opt, self.original_type)) for opt in self.options
        ]


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
