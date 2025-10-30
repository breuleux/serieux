import importlib
import inspect
import typing
from dataclasses import MISSING, dataclass, replace
from functools import cached_property, partial
from typing import Annotated, Any

from ovld import call_next

from .docstrings import get_variable_data
from .instructions import BaseInstruction, inherit, strip
from .model import Field, Model, model
from .utils import evaluate_hint


class MeldedCall:
    def __init__(self, *funcs):
        self.steps = [
            (
                func,
                (params := list(inspect.signature(func).parameters.values())[min(i, 1) :]),
                set(p.name for p in params),
            )
            for i, func in enumerate(funcs)
        ]

    def __call__(self, **kwargs):
        current = inspect._empty
        for fn, _, argnames in self.steps:
            args = {an: kwargs[an] for an in argnames if an in kwargs}
            if current is inspect._empty:
                current = fn(**args)
            else:
                current = fn(current, **args)
        return current

    @cached_property
    def __variable_data__(self):
        vd = {}
        for fn, _, _ in self.steps:
            vd.update(get_variable_data(fn))
        return vd

    @cached_property
    def __signature__(self):
        final_params = []
        seen = set()
        for _, params, _ in self.steps:
            for param in params:
                if param.name not in seen:
                    seen.add(param.name)
                    new_param = param.replace(kind=inspect.Parameter.KEYWORD_ONLY)
                    final_params.append(new_param)
        return inspect.Signature(final_params)


@dataclass(frozen=True)
class Auto(BaseInstruction):
    call: bool = False
    embed_self: bool = True
    force: bool = False

    @property
    def annotation_priority(self):  # pragma: no cover
        return 1

    def __class_getitem__(cls, t):
        return cls()[t]

    def __getitem__(self, t):
        return Annotated[t, self]

    __call__ = replace


Call = Auto(call=True)


def model_from_callable(t, call=False, embed_self=True):
    orig_t, t = t, strip(t)
    if t is Any:
        return None
    if isinstance(t, type) and call:
        raise TypeError("Call[...] should only wrap callables")
    sig = inspect.signature(t)
    fields = []
    docs = get_variable_data(t)
    positionals = []
    for param in sig.parameters.values():
        meta = {}
        if param.kind == inspect.Parameter.POSITIONAL_ONLY:
            meta["positional"] = True
            positionals.append(param.name)
        if param.name in docs:
            meta.update(docs[param.name].metadata)
        if param.name == "self" and param.annotation in (inspect._empty, typing.Self):
            parent_class = getattr(
                importlib.import_module(t.__module__), t.__qualname__.split(".")[0]
            )
            if embed_self:
                return model_from_callable(
                    MeldedCall(parent_class, t), call=call, embed_self=False
                )
            else:
                param = param.replace(annotation=parent_class)
        if param.annotation is inspect._empty:
            raise TypeError(f"Cannot model {t}: parameter '{param.name}' lacks a type annotation.")
        field = Field(
            name=param.name,
            description=(docs[param.name].doc or None) if param.name in docs else None,
            metadata=meta,
            type=inherit(orig_t, evaluate_hint(param.annotation, None, None, None)),
            default=MISSING if param.default is inspect._empty else param.default,
            argument_name=param.name,
            property_name=None,
        )
        fields.append(field)

    if not isinstance(t, type) and not call:

        def build(*args, **kwargs):
            return partial(t, *args, **kwargs)

    else:
        build = t

    if positionals:

        def constructor(**kwargs):
            args = [kwargs.pop(k) for k in positionals]
            return build(*args, **kwargs)
    else:
        constructor = build

    return Model(
        original_type=t,
        fields=fields,
        constructor=constructor,
    )


@model.register(priority=-1)
def _(t: type[Any @ Auto]):
    _, aut = Auto.decompose(t)
    aut = aut or Auto()
    if not aut.call and not aut.force and (normal := call_next(t)) is not None:
        return normal
    return model_from_callable(t, call=aut.call, embed_self=aut.embed_self)
