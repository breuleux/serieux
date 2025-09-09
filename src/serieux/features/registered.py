import importlib
from dataclasses import dataclass, field
from typing import Any

from ovld import Medley, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import BaseInstruction
from ..model import Model, model
from ..priority import HI2


class BaseRegistry(BaseInstruction):  # pragma: no cover
    def from_symbol(self, item):
        raise NotImplementedError()

    def to_symbol(self, item):
        raise NotImplementedError()

    def iterate(self):
        raise NotImplementedError()

    def closed(self):
        return True

    def __class_getitem__(cls, item):
        return item @ cls()


@dataclass(eq=False)
class Registry(BaseRegistry):
    registry: dict[str, Any] = field(default_factory=dict)
    inverse_registry: dict[Any, str] = None
    inverse: bool = True

    def __post_init__(self):
        if self.inverse and self.inverse_registry is None and self.inverse:
            self.inverse_registry = {v: k for k, v in self.registry.items()}

    def register(self, item, value):
        self.registry[item] = value
        if self.inverse:
            self.inverse_registry[value] = item
        return value

    def from_symbol(self, item):
        if item in self.registry:
            return self.registry[item]
        else:
            raise ValidationError(
                f"{item!r} is not a registered option. Should be one of: {list(self.registry.keys())}"
            )

    def to_symbol(self, value):
        if self.inverse and value in self.inverse_registry:
            return self.inverse_registry[value]
        else:
            raise ValidationError(
                f"The value {value!r} is not registered under any name in the mapping"
            )

    def iterate(self):
        yield from self.registry.keys()


class Referenced(BaseRegistry):
    def from_symbol(self, item):
        mod_name, _, class_name = item.partition(":")
        mod = importlib.import_module(mod_name)
        return getattr(mod, class_name) if class_name else mod

    def to_symbol(self, value):
        if hasattr(value, "__qualname__"):
            return f"{value.__module__}:{value.__qualname__}"
        else:
            raise ValidationError(f"Cannot find a module:symbol reference for the value {value!r}")

    def iterate(self):  # pragma: no cover
        yield from []

    def closed(self):  # pragma: no cover
        return False


class AutoRegistered:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "_registry"):
            cls._registry = Registry()

    def __init__(self, registered_name):
        self.registered_name = registered_name
        type(self)._registry.register(registered_name, self)


def auto_singleton(arg, /):
    def wrap(cls):
        if (
            not isinstance(cls, type)
            or not issubclass(cls, AutoRegistered)
            or AutoRegistered in cls.__bases__
        ):
            raise TypeError(
                "@singleton must wrap a class definition and the class must be"
                " a subclass of Registered, but not a direct subclass."
            )
        return cls(registered_name=registered_name)

    if isinstance(arg, str):
        registered_name = arg
        return wrap
    else:
        registered_name = arg.__name__.lower()
        return wrap(arg)


class RegisteredHandler(Medley):
    @ovld(priority=HI2)
    def schema(self, t: type[AutoRegistered], ctx: Context, /):
        return {"type": "string", "enum": list(t._registry.iterate())}


@model.register
def _(t: type[Any @ BaseRegistry]):  # noqa: F821
    rg = BaseRegistry.extract(t)
    if not rg:
        return None
    return Model(
        original_type=t,
        from_string=rg.from_symbol,
        to_string=rg.to_symbol,
    )


@model.register
def _(t: type[AutoRegistered]):  # noqa: F821
    if not hasattr(t, "_registry"):
        return None
    return recurse(t @ t._registry)
