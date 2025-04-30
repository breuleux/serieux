import inspect
from dataclasses import MISSING

from ovld import call_next

from .docstrings import get_variable_data
from .instructions import NewInstruction
from .model import Field, Model, model
from .utils import evaluate_hint

Auto = NewInstruction["Auto", -1, True]


def model_from_callable(t):
    sig = inspect.signature(t)
    fields = []
    docs = get_variable_data(t)
    for param in sig.parameters.values():
        if param.annotation is inspect._empty:
            raise Exception(f"Missing type annotation for argument '{param.name}'.")
        field = Field(
            name=param.name,
            description=docs.get(param.name, param.name),
            type=Auto[evaluate_hint(param.annotation, None, None, None)],
            default=MISSING if param.default is inspect._empty else param.default,
            argument_name=param.name,
            property_name=None,
        )
        fields.append(field)
    return Model(
        original_type=t,
        fields=fields,
        constructor=t,
    )


@model.register(priority=-1)
def _(t: type[Auto]):
    if (normal := call_next(t)) is not None:
        return normal
    try:
        return model_from_callable(Auto.strip(t))
    except Exception:
        return None
