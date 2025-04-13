import importlib

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import NewInstruction

#############
# Constants #
#############

TaggedSubclass = NewInstruction["TaggedSubclass"]


###################
# Implementations #
###################


def _resolve(ref, base, ctx):
    if ref is None:
        return base

    if (ncolon := ref.count(":")) == 0:
        mod_name = base.__module__
        symbol = ref
    elif ncolon == 1:
        mod_name, symbol = ref.split(":")
    else:
        raise ValidationError(f"Bad format for class reference: '{ref}'", ctx=ctx)
    try:
        mod = importlib.import_module(mod_name)
        return getattr(mod, symbol)
    except (ModuleNotFoundError, AttributeError) as exc:
        raise ValidationError(exc=exc, ctx=ctx)


class TaggedSubclassFeature(Medley):
    @ovld(priority=10)
    def serialize(self, t: type[TaggedSubclass], obj: object, ctx: Context, /):
        base = t.pushdown()
        if not isinstance(obj, base):
            raise ValidationError(f"'{obj}' is not a subclass of '{base}'", ctx=ctx)
        objt = type(obj)
        qn = objt.__qualname__
        if "." in qn:
            raise ValidationError("Only top-level symbols can be serialized", ctx=ctx)
        mod = objt.__module__
        rval = call_next(objt, obj, ctx)
        rval["class"] = f"{mod}:{qn}"
        return rval

    def deserialize(self, t: type[TaggedSubclass], obj: dict, ctx: Context, /):
        base = t.pushdown()
        obj = dict(obj)
        cls_name = obj.pop("class", None)
        actual_class = _resolve(cls_name, base, ctx)
        if not issubclass(actual_class, base):
            raise ValidationError(f"'{obj}' is not a subclass of '{base}'", ctx=ctx)
        return recurse(actual_class, obj, ctx)


# Add as a default feature in serieux.Serieux
__default_features__ = TaggedSubclassFeature
