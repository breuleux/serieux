from dataclasses import dataclass
from typing import Annotated, Any

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import BaseInstruction
from ..priority import HI6
from ..proxy import ProxyBase
from ..schema import AnnotatedSchema
from .tagset import value_field

#############
# Constants #
#############


comment_field = "$comment"


class CommentProxy(ProxyBase):
    def __init__(self, obj, comment):
        self._obj = obj
        self._type = type(obj)
        self._ = comment


@dataclass(frozen=True)
class Comment(BaseInstruction):
    comment_type: type
    required: bool = False
    inherit: bool = False

    def __class_getitem__(cls, args):
        t, ct = args
        return Annotated[t, cls(ct)]


@dataclass(frozen=True)
class CommentRec(Comment):
    inherit: bool = True


class StripComments(Context):
    """Context to ignore the data commenting feature."""


###################
# Implementations #
###################


class CommentedObjects(Medley):
    @ovld(priority=HI6)
    def serialize(self, t: type[Any @ Comment], obj: CommentProxy, ctx: Context):
        base, instr = Comment.decompose(t)
        rval = recurse(base, obj._obj, ctx)
        if isinstance(ctx, StripComments):
            return rval
        comment = recurse(instr.comment_type, obj._, ctx)
        if not isinstance(rval, dict):
            rval = {value_field: rval}
        rval[comment_field] = comment
        return rval

    @ovld(priority=HI6)
    def serialize(self, t: type[Any @ Comment], obj: object, ctx: Context):
        instr = Comment.extract(t)
        if instr.required and not isinstance(ctx, StripComments):
            raise ValidationError("Comment is required but object is not a CommentProxy", ctx=ctx)
        return call_next(t, obj, ctx)

    @ovld(priority=HI6)
    def serialize(self, t: Any, obj: CommentProxy, ctx: Context):
        return recurse(t, obj._obj, ctx)

    @ovld(priority=HI6)
    def deserialize(self, t: type[Any @ Comment], obj: dict, ctx: Context):
        base, instr = Comment.decompose(t)
        if comment_field not in obj:
            if instr.required:
                raise ValidationError(
                    f"Comment is required but '{comment_field}' field is missing", ctx=ctx
                )
            return call_next(t, obj, ctx)
        obj = dict(obj)
        comment = obj.pop(comment_field)
        if value_field in obj:
            obj = obj.pop(value_field)
        main = recurse(base, obj, ctx)
        if isinstance(ctx, StripComments):
            return main
        comment = recurse(instr.comment_type, comment, ctx)
        return CommentProxy(main, comment)

    @ovld(priority=HI6)
    def deserialize(self, t: type[Any @ Comment], obj: object, ctx: Context):
        instr = Comment.extract(t)
        if instr.required and not isinstance(ctx, StripComments):
            raise ValidationError(
                f"Comment is required but input is not a dictionary with '{comment_field}' field",
                ctx=ctx,
            )
        return call_next(t, obj, ctx)

    @ovld
    def schema(self, t: type[Any @ Comment], ctx: Context):
        base, instr = Comment.decompose(t)
        base_schema = recurse(base, ctx)
        if isinstance(ctx, StripComments):
            return base_schema
        comment_schema = recurse(instr.comment_type, ctx)
        if base_schema.get("type", None) == "object":
            return AnnotatedSchema(
                base_schema,
                properties={comment_field: comment_schema},
                required=[comment_field] if instr.required else [],
            )
        else:
            required = [value_field]
            if instr.required:
                required.append(comment_field)
            return {
                "type": "object",
                "properties": {
                    value_field: base_schema,
                    comment_field: comment_schema,
                },
                "required": required,
            }
