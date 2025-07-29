from dataclasses import dataclass
from typing import Annotated, Any, Union, get_args

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import BaseInstruction, strip
from ..tell import KeyValueTell, TypeTell, tells
from ..utils import PRIO_HIGH


@dataclass(frozen=True)
class Tagged(BaseInstruction):
    tag: str
    annotation_priority = 1

    def __class_getitem__(cls, arg):
        match arg:
            case (t, name):
                return Annotated[t, cls(name)]
            case t:
                t = strip(t)
                tag = getattr(t, "__tag__", None) or t.__name__.lower()
                return Annotated[t, cls(tag)]


class TaggedUnion(type):
    def __class_getitem__(cls, args):
        if isinstance(args, dict):
            return Union[tuple(Tagged[v, k] for k, v in args.items())]
        elif not isinstance(args, (list, tuple)):
            return Tagged[args]
        return Union[tuple(Tagged[arg] for arg in args)]


@tells.register
def tells(typ: type[Any @ Tagged]):
    tag = Tagged.extract(typ)
    return {TypeTell(dict), KeyValueTell("class", tag.tag)}


class TaggedTypes(Medley):
    @ovld(priority=PRIO_HIGH)
    def serialize(self, t: type[Any @ Tagged], obj: object, ctx: Context, /):
        tag = Tagged.extract(t)
        cls = get_args(t)[0]
        result = call_next(cls, obj, ctx)
        if not isinstance(result, dict):
            result = {"return": result}
        result["class"] = tag.tag
        return result

    @ovld(priority=PRIO_HIGH)
    def deserialize(self, t: type[Any @ Tagged], obj: dict, ctx: Context, /):
        tag = Tagged.extract(t)
        cls = get_args(t)[0]
        obj = dict(obj)
        found = recurse(str, obj.pop("class", None), ctx)
        if "return" in obj:
            obj = obj["return"]
        if found != tag.tag:  # pragma: no cover
            raise ValidationError(
                f"Cannot deserialize into '{t}' because we found incompatible tag {found!r}",
                ctx=ctx,
            )
        return recurse(cls, obj, ctx)


# Add as a default feature in serieux.Serieux
__default_features__ = TaggedTypes
