from types import NoneType
from typing import Any, get_args, get_origin

from ovld import (
    Code,
    CodegenInProgress,
    Lambda,
    OvldPerInstanceBase,
    code_generator,
    current_code,
    ovld,
    recurse,
)
from ovld.types import All

from .model import model
from .state import State, empty


def standard_code_generator(fn):
    fn.standard_codegen = True
    return code_generator(fn)


class BaseTransformer(OvldPerInstanceBase):
    validate_by_default = True

    def __init__(self, validate=None):
        self.validate = self.validate_by_default if validate is None else validate

    @classmethod
    def ovld_instance_key(cls, validate=None):
        validate = cls.validate_by_default if validate is None else validate
        return (("this", cls), ("validate", validate))

    ###########
    # helpers #
    ###########

    def embed_condition(self, t):
        if t in (int, str, bool, float, NoneType):
            return t

    def subcode(self, t, accessor, state_t, after=None, default=True, objt=None):
        if objt is not None:
            ec = objt
        elif ec := self.embed_condition(t):
            ec = All[ec]
        if ec is not None:
            try:
                fn = self.transform.resolve(type[t], ec, state_t, after=after)
                cg = getattr(fn, "__codegen__", None)
                if cg:
                    return cg.create_expression([None, t, accessor, "$state"])
            except (CodegenInProgress, ValueError):
                pass
        return self.default_codegen(t, accessor) if default else None

    def guard_codegen(self, t, accessor, body):
        if not self.validate:
            return Code(body)
        else:
            return Code(
                "$body if isinstance($accessor, $t) else $dflt",
                body=Code(body),
                accessor=Code(accessor),
                t=t,
                dflt=self.default_codegen(t, accessor),
            )

    def default_codegen(self, t, accessor):
        return Code(
            "$recurse($t, $accessor, $state)",
            t=t,
            accessor=accessor if isinstance(accessor, Code) else Code(accessor),
            recurse=self.transform,
        )

    ######################
    # transform: codegen #
    ######################

    @ovld
    @standard_code_generator
    def transform(self, t: type[object], obj: Any, state: State, /):
        (t,) = get_args(t)
        mt = model(t)
        if mt == t:
            return None
        else:
            nxt = self.transform.resolve(type[mt], obj, state, after=current_code)
            return getattr(nxt, "__codegen__", None)

    for T in (int, str, bool, float, NoneType):

        @standard_code_generator
        def transform(self, t: type[T], obj: T, state: State, /):
            (t,) = get_args(t)
            return Lambda(self.guard_codegen(t, "$obj", "$obj"))

    @standard_code_generator
    def transform(self, t: type[list], obj: list, state: State, /):
        (t,) = get_args(t)
        (lt,) = get_args(t)
        return Lambda(
            self.guard_codegen(get_origin(t), "$obj", "[$lbody for X in $obj]"),
            lbody=self.subcode(lt, "X", state),
        )

    @standard_code_generator
    def transform(self, t: type[dict], obj: dict, state: State, /):
        (t,) = get_args(t)
        kt, vt = get_args(t)
        return Lambda(
            "{$kbody: $vbody for K, V in $obj.items()}",
            kbody=self.subcode(kt, "K", state),
            vbody=self.subcode(vt, "V", state),
        )

    ###########################
    # transform: entry points #
    ###########################

    def transform(self, obj: object, /):
        return recurse(type(obj), obj, empty)

    def transform(self, t: type[object], obj: object, /):
        return recurse(t, obj, empty)
