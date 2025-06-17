import importlib
from collections import deque
from typing import TYPE_CHECKING, Annotated, TypeAlias

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import NewInstruction, T, strip_all
from ..schema import AnnotatedSchema

#############
# Constants #
#############


if TYPE_CHECKING:
    TaggedSubclass: TypeAlias = Annotated[T, None]
else:
    TaggedSubclass: TypeAlias = NewInstruction[T, "TaggedSubclass", 1, False]


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
        if cls_name is not None:
            cls_name = recurse(str, cls_name, ctx)
        actual_class = _resolve(cls_name, base, ctx)
        if not issubclass(actual_class, base):
            raise ValidationError(f"'{actual_class}' is not a subclass of '{base}'", ctx=ctx)
        return recurse(TaggedSubclass.strip(t[actual_class]), obj, ctx)

    def schema(self, t: type[TaggedSubclass], ctx: Context):
        base = strip_all(t)
        subschemas = []
        base_mod = base.__module__
        queue = deque([base])
        while queue:
            sc = queue.popleft()
            queue.extend(sc.__subclasses__())
            sc_mod = sc.__module__
            sc_name = sc.__name__
            subsch = recurse(TaggedSubclass.strip(t[sc]))
            subsch = AnnotatedSchema(
                parent=subsch,
                properties={
                    "class": {
                        "description": "Reference to the class to instantiate",
                        "const": sc_name if sc_mod == base_mod else f"{sc_mod}:{sc_name}",
                    }
                },
                required=[] if sc is base else ["class"],
            )
            subschemas.append(subsch)
        return {"oneOf": subschemas}


# Add as a default feature in serieux.Serieux
__default_features__ = TaggedSubclassFeature
