import inspect
from dataclasses import MISSING
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, TypeAlias

from ovld import call_next

from .docstrings import get_variable_data
from .instructions import Instruction, T, strip
from .model import Field, Model, model
from .utils import evaluate_hint

if TYPE_CHECKING:
    Call: TypeAlias = Annotated[T, None]
    Auto: TypeAlias = Annotated[T, None]
else:
    Call = Instruction("Call", annotation_priority=-1, inherit=True)
    Auto = Instruction("Auto", annotation_priority=-1, inherit=True)


def model_from_callable(t, call=False):
    if t is Any:
        return None
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
def _(t: type[Any @ Auto]):
    if (normal := call_next(t)) is not None:
        return normal
    return model_from_callable(strip(t))


@model.register(priority=-1)
def _(t: type[Any @ Call]):
    return model_from_callable(strip(t), True)
