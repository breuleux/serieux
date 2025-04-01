import importlib
from typing import TYPE_CHECKING, Annotated, TypeVar

from ovld import Medley, call_next, ovld, recurse

from .ctx import Context
from .typetags import make_tag

#############
# Constants #
#############

if TYPE_CHECKING:  # pragma: no cover
    T = TypeVar("T")
    TaggedSubclass = Annotated[T, None]
else:
    TaggedSubclass = make_tag("TaggedSubclass", 1)


###################
# Implementations #
###################


def _resolve(ref, base):
    if ref is None:
        return base

    if (ncolon := ref.count(":")) == 0:
        mod_name = base.__module__
        symbol = ref
    elif ncolon == 1:
        mod_name, symbol = ref.split(":")
    else:
        raise Exception(f"Bad format for class reference: {ref}")
    try:
        mod = importlib.import_module(mod_name)
        return getattr(mod, symbol)
    except (ModuleNotFoundError, AttributeError) as exc:
        raise Exception(str(exc))


class TaggedSubclassFeature(Medley):
    @ovld(priority=10)
    def serialize(self, t: type[TaggedSubclass], obj: object, ctx: Context, /):
        base = t.pushdown()
        if not isinstance(obj, base):
            raise TypeError(f"'{obj}' is not a subclass of '{base}'")
        objt = type(obj)
        qn = objt.__qualname__
        assert "." not in qn, "Only top-level symbols can be serialized"
        mod = objt.__module__
        rval = call_next(objt, obj, ctx)
        rval["class"] = f"{mod}:{qn}"
        return rval

    def deserialize(self, t: type[TaggedSubclass], obj: dict, ctx: Context, /):
        base = t.pushdown()
        obj = dict(obj)
        cls_name = obj.pop("class", None)
        actual_class = _resolve(cls_name, base)
        return recurse(actual_class, obj, ctx)
