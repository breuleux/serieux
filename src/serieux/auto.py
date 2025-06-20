import inspect
from dataclasses import MISSING
from functools import partial
from typing import TYPE_CHECKING, Annotated, TypeAlias

from ovld import call_next

from .docstrings import get_variable_data
from .instructions import NewInstruction, T
from .model import Field, Model, model
from .utils import evaluate_hint

if TYPE_CHECKING:
    Call: TypeAlias = Annotated[T, None]
    Auto: TypeAlias = Annotated[T, None]
else:
    Call = NewInstruction[T, "Call", -1, True]
    Auto = NewInstruction[T, "Auto", -1, True]


def model_from_callable(t, call=False):
    if isinstance(t, type) and call:
        raise TypeError("Call[...] should only wrap callables")
    try:
        sig = inspect.signature(t)
    except ValueError:
        return None
    fields = []
    docs = get_variable_data(t)
    for param in sig.parameters.values():
        if param.annotation is inspect._empty:
            return None
        field = Field(
            name=param.name,
            description=(docs[param.name].doc or param.name) if param.name in docs else param.name,
            metadata=(docs[param.name].metadata or {}) if param.name in docs else {},
            type=Auto[evaluate_hint(param.annotation, None, None, None)],
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

    return Model(
        original_type=t,
        fields=fields,
        constructor=build,
    )


@model.register(priority=-1)
def _(t: type[Auto]):
    if (normal := call_next(t)) is not None:
        return normal
    return model_from_callable(Auto.strip(t))


@model.register(priority=-1)
def _(t: type[Call]):
    return model_from_callable(Call.strip(t), True)
