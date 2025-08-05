import inspect
from dataclasses import MISSING, dataclass
from functools import partial
from typing import Annotated, Any

from ovld import call_next

from .docstrings import get_variable_data
from .instructions import BaseInstruction, inherit, strip
from .model import Field, Model, model
from .utils import evaluate_hint


@dataclass(frozen=True)
class Auto(BaseInstruction):
    call: bool = False
    partial: bool = True

    @property
    def annotation_priority(self):  # pragma: no cover
        return 1

    def __class_getitem__(cls, t):
        return cls()[t]

    def __getitem__(self, t):
        return Annotated[t, self]


Call = Auto(call=True, partial=False)


def model_from_callable(t, call=False):
    orig_t, t = t, strip(t)
    if t is Any:
        return None
    if isinstance(t, type) and call:
        raise TypeError("Call[...] should only wrap callables")
    sig = inspect.signature(t)
    fields = []
    docs = get_variable_data(t)
    for param in sig.parameters.values():
        if param.annotation is inspect._empty:
            return None
        field = Field(
            name=param.name,
            description=(docs[param.name].doc or param.name) if param.name in docs else param.name,
            metadata=(docs[param.name].metadata or {}) if param.name in docs else {},
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

    return Model(
        original_type=t,
        fields=fields,
        constructor=build,
    )


@model.register(priority=-1)
def _(t: type[Any @ Auto]):
    _, aut = Auto.decompose(t)
    aut = aut or Auto()
    if not aut.call and (normal := call_next(t)) is not None:
        return normal
    return model_from_callable(t, call=aut.call)
