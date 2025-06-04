import importlib

from ovld import Exactly, Medley, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..utils import PRIO_LOW

###################
# Implementations #
###################


def _resolve(ref, ctx):
    if ref is None:
        raise ValidationError("There must be a class reference to resolve.", ctx=ctx)

    if (ncolon := ref.count(":")) == 0:
        raise ValidationError(f"Class reference must include module: '{ref}'", ctx=ctx)
    elif ncolon == 1:
        mod_name, symbol = ref.split(":")
    else:
        raise ValidationError(f"Bad format for class reference: '{ref}'", ctx=ctx)
    try:
        mod = importlib.import_module(mod_name)
        return getattr(mod, symbol)
    except (ModuleNotFoundError, AttributeError) as exc:
        raise ValidationError(exc=exc, ctx=ctx)


class AutoTagAny(Medley):
    @ovld(priority=PRIO_LOW)
    def serialize(self, t: type[Exactly[object]], obj: object, ctx: Context, /):
        objt = type(obj)
        qn = objt.__qualname__
        if "." in qn:
            raise ValidationError("Only top-level symbols can be serialized", ctx=ctx)
        mod = objt.__module__
        rval = recurse(objt, obj, ctx)
        if not isinstance(rval, dict):
            rval = {"return": rval}
        rval["class"] = f"{mod}:{qn}"
        return rval

    @ovld(priority=PRIO_LOW)
    def deserialize(self, t: type[Exactly[object]], obj: dict, ctx: Context, /):
        obj = dict(obj)
        cls_name = obj.pop("class", None)
        obj = obj.pop("return", obj)
        if cls_name is not None:
            cls_name = recurse(str, cls_name, ctx)
        actual_class = _resolve(cls_name, ctx)
        assert actual_class
        return recurse(actual_class, obj, ctx)


# Not a default feature
__default_features__ = None
