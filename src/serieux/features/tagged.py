from functools import reduce
from operator import or_
from typing import TYPE_CHECKING, TypeAlias, Union

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import strip_all
from ..tell import KeyValueTell, TypeTell, tells
from ..utils import PRIO_HIGH, clsstring

if TYPE_CHECKING:  # pragma: no cover
    from typing import Annotated

    Tagged: TypeAlias = Annotated
    TaggedUnion = Union

else:

    class Tagged(type):
        def __subclasscheck__(cls, other):
            return issubclass(other, cls.cls)

        def __instancecheck__(cls, obj):
            return isinstance(obj, cls.cls)

        def __class_getitem__(cls, args):
            if isinstance(args, (list, tuple)):
                cls, tag = args
            else:
                cls = args
                clsn = strip_all(cls)
                tag = getattr(clsn, "__tag__", None) or clsn.__name__.lower()
            return Tagged(
                f"{tag}::{clsstring(cls)}",
                (Tagged,),
                # Set module to None for better display
                {"cls": cls, "tag": tag, "__module__": None},
            )

    class TaggedUnion(type):
        def __class_getitem__(cls, args):
            if isinstance(args, dict):
                return reduce(or_, [Tagged[v, k] for k, v in args.items()])
            elif not isinstance(args, (list, tuple)):
                return Tagged[args]
            return reduce(or_, [Tagged[arg] for arg in args])


@tells.register
def tells(typ: type[Tagged]):
    return {TypeTell(dict), KeyValueTell("class", typ.tag)}


class TaggedTypes(Medley):
    @ovld(priority=PRIO_HIGH)
    def serialize(self, t: type[Tagged], obj: object, ctx: Context, /):
        result = call_next(t.cls, obj, ctx)
        if not isinstance(result, dict):
            result = {"return": result}
        result["class"] = t.tag
        return result

    @ovld(priority=PRIO_HIGH)
    def deserialize(self, t: type[Tagged], obj: dict, ctx: Context, /):
        obj = dict(obj)
        found = recurse(str, obj.pop("class", None), ctx)
        if "return" in obj:
            obj = obj["return"]
        if found != t.tag:  # pragma: no cover
            raise ValidationError(
                f"Cannot deserialize into '{t}' because we found incompatible tag {found!r}",
                ctx=ctx,
            )
        return recurse(t.cls, obj, ctx)


# Add as a default feature in serieux.Serieux
__default_features__ = TaggedTypes
