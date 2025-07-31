from dataclasses import dataclass
from typing import Annotated, Any

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import BaseInstruction
from ..schema import AnnotatedSchema
from ..utils import PRIO_HIGHER
from .proxy import CommentProxy
from .tagset import value_field

#############
# Constants #
#############


comment_field = "$comment"


@dataclass(frozen=True)
class Comment(BaseInstruction):
    comment_type: type
    required: bool = False

    def __class_getitem__(cls, args):
        t, ct = args
        return Annotated[t, Comment(ct)]


###################
# Implementations #
###################


class CommentedObjects(Medley):
    @ovld(priority=PRIO_HIGHER - 1)
    def serialize(self, t: type[Any @ Comment], obj: CommentProxy, ctx: Context):
        base, instr = Comment.decompose(t)
        rval = recurse(base, obj._obj, ctx)
        comment = recurse(instr.comment_type, obj._, ctx)
        if not isinstance(rval, dict):
            rval = {value_field: rval}
        rval[comment_field] = comment
        return rval

    @ovld(priority=PRIO_HIGHER - 1)
    def serialize(self, t: type[Any @ Comment], obj: object, ctx: Context):
        instr = Comment.extract(t)
        if instr.required:
            raise ValidationError("Comment is required but object is not a CommentProxy", ctx=ctx)
        return call_next(t, obj, ctx)

    @ovld(priority=PRIO_HIGHER - 1)
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
        comment = recurse(instr.comment_type, comment, ctx)
        return CommentProxy(main, comment)

    @ovld(priority=PRIO_HIGHER - 1)
    def deserialize(self, t: type[Any @ Comment], obj: object, ctx: Context):
        instr = Comment.extract(t)
        if instr.required:
            raise ValidationError(
                f"Comment is required but input is not a dictionary with '{comment_field}' field",
                ctx=ctx,
            )
        return call_next(t, obj, ctx)

    @ovld
    def schema(self, t: type[Any @ Comment], ctx: Context):
        base, instr = Comment.decompose(t)
        base_schema = recurse(base, ctx)
        comment_schema = recurse(instr.comment_type, ctx)
        return AnnotatedSchema(
            base_schema,
            properties={comment_field: comment_schema},
            required=[comment_field] if instr.required else [],
        )
