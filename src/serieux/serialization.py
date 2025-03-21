from types import NoneType
from typing import Any, get_args, get_origin

from ovld import (
    Code,
    CodegenInProgress,
    Lambda,
    OvldPerInstanceBase,
    current_code,
    ovld,
    recurse,
    subclasscheck,
)
from ovld.types import All

from .model import Modell as Model, model
from .state import State, empty
from .transform import standard_code_generator
from .typetags import strip_all
from .utils import UnionAlias


class Serializer(OvldPerInstanceBase):
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

    def valtype(self, t):
        if subclasscheck(t, UnionAlias):
            return All
        else:
            return All[t]

    def subcode(self, t, accessor, state_t, after=None, default=True):
        try:
            fn = self.transform.resolve(type[t], self.valtype(t), state_t, after=after)
            lbda = getattr(fn, "__lambda__", None)
            if lbda:
                return lbda(None, t, accessor, "$state")
        except CodegenInProgress:
            pass
        return self.default_codegen(t, accessor) if default else None

    def default_codegen(self, t, accessor):
        return Code(
            "$recurse($t, $accessor, $state)",
            t=t,
            accessor=Code(accessor),
            recurse=self.transform,
        )

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

    ######################
    # transform: codegen #
    ######################

    @ovld(priority=1)
    @standard_code_generator
    def transform(self, t: type[object], obj: Any, state: State, /):
        (t,) = get_args(t)
        mt = model(t)
        if mt == t:
            return None
        else:
            code = self.subcode(mt, "$obj", state, after=current_code)
            return code and Lambda(code)

    for T in (int, str, bool, float, NoneType):

        @standard_code_generator
        def transform(self, t: type[T], obj: T, state: State, /):
            (t,) = get_args(t)
            return Lambda(self.guard_codegen(t, "$obj", "$obj"))

    @standard_code_generator
    def transform(self, t: type[Model], obj: Model, state: State, /):
        (t,) = get_args(t)
        return Lambda(
            "{$[,]parts}",
            parts=[
                Code(
                    "$fname: $setter",
                    fname=f.serialized_name,
                    setter=self.subcode(f.type, f"$obj.{f.property_name}", state),
                )
                for f in t.fields
            ],
        )

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

    @standard_code_generator
    def transform(self, t: type[UnionAlias], obj: Any, state: State, /):
        (t,) = get_args(t)
        o1, *rest = get_args(t)
        code = self.subcode(o1, "$obj", state)
        for opt in rest:
            code = Code(
                "$ocode if isinstance($obj, $sopt) else $code",
                sopt=strip_all(opt),
                ocode=self.subcode(opt, "$obj", state),
                code=code,
            )
        return Lambda(code)

    ###########################
    # transform: entry points #
    ###########################

    def transform(self, obj: object, /):
        return recurse(type(obj), obj, empty)

    def transform(self, t: type[object], obj: object, /):
        return recurse(t, obj, empty)


default = Serializer()
serialize = default.transform

default_check = Serializer(validate=True)
serialize_check = default_check.transform
