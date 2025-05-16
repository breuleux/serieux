from typing import Any

from ovld import Medley, ovld

from ..ctx import Context
from ..exc import ValidationError
from ..utils import PRIO_HIGH


class RegisteredMC(type):
    def __init__(cls, name, bases, ns):
        super().__init__(name, bases, ns)
        if not hasattr(cls, "_registered_mapping") and bases != (SMBase,):
            cls._registered_mapping = {}
            cls._registered_inverse_mapping = {}


class SMBase:
    @staticmethod
    def create(name, mapping):
        inv_mapping = {v: k for k, v in mapping.items()}
        return RegisteredMC(
            name,
            (Registered,),
            {"_registered_mapping": mapping, "_registered_inverse_mapping": inv_mapping},
        )


class Registered(SMBase, metaclass=RegisteredMC):
    def __init__(self, registered_name):
        self.registered_name = registered_name
        type(self)._registered_mapping[registered_name] = self
        type(self)._registered_inverse_mapping[self] = registered_name


def singleton(arg, /):
    def wrap(cls):
        if (
            not isinstance(cls, type)
            or not issubclass(cls, Registered)
            or Registered in cls.__bases__
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


class StringMappedMC(RegisteredMC):
    def __init__(cls, name, bases, ns):
        regs = {k: v for k, v in ns.items() if not k.startswith("__")}
        super().__init__(name, bases, ns)
        if regs:
            cls._registered_mapping.update(regs)
            cls._registered_inverse_mapping.update({v: k for k, v in regs.items()})


class StringMapped(SMBase, metaclass=StringMappedMC):
    pass


class RegisteredHandler(Medley):
    @ovld(priority=PRIO_HIGH + 1)
    def deserialize(self, t: type[SMBase], obj: str, ctx: Context, /):
        mapping = t._registered_mapping
        if obj in mapping:
            return mapping[obj]
        else:
            raise ValidationError(
                f"'{obj}' is not a registered option. Should be one of: {list(mapping.keys())}"
            )

    @ovld(priority=PRIO_HIGH + 1)
    def serialize(self, t: type[SMBase], obj: Any, ctx: Context, /):
        inv_mapping = t._registered_inverse_mapping
        if obj in inv_mapping:
            return inv_mapping[obj]
        else:
            raise ValidationError(
                f"The value '{obj}' is not registered under any name in the mapping"
            )

    @ovld(priority=PRIO_HIGH + 1)
    def schema(self, t: type[SMBase], ctx: Context, /):
        return {"type": "string", "enum": list(t._registered_mapping.keys())}


# Add as a default feature in serieux.Serieux
__default_features__ = RegisteredHandler
