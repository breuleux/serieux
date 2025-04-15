from typing import TYPE_CHECKING, TypeAlias

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..tell import KeyValueTell, TypeTell, tells
from ..utils import clsstring

if TYPE_CHECKING:  # pragma: no cover
    from typing import Annotated

    Tagged: TypeAlias = Annotated

else:

    class Tagged(type):
        def __subclasscheck__(cls, other):
            return issubclass(other, cls.cls)

        def __instancecheck__(cls, obj):
            return isinstance(obj, cls.cls)

        def __class_getitem__(cls, args):
            cls, tag = args
            return Tagged(
                f"{tag}::{clsstring(cls)}",
                (Tagged,),
                # Set module to None for better display
                {"cls": cls, "tag": tag, "__module__": None},
            )


@tells.register
def tells(typ: type[Tagged]):
    return {TypeTell(dict), KeyValueTell("class", typ.tag)}


class TaggedTypes(Medley):
    @ovld(priority=10)
    def serialize(self, t: type[Tagged], obj: object, ctx: Context, /):
        result = call_next(t.cls, obj, ctx)
        if not isinstance(result, dict):
            result = {"return": result}
        result["class"] = t.tag
        return result

    @ovld(priority=10)
    def deserialize(self, t: type[Tagged], obj: dict, ctx: Context, /):
        obj = dict(obj)
        klas = obj.pop("class", None)
        if "return" in obj:
            obj = obj["return"]
        assert klas == t.tag
        return recurse(t.cls, obj, ctx)


# Add as a default feature in serieux.Serieux
__default_features__ = TaggedTypes
