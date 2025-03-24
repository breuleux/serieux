from typing import Any, get_args, get_origin

from ovld import Code, Lambda, extend_super, subclasscheck

from .base import BaseTransformer, standard_code_generator
from .model import Modell as Model
from .state import State
from .typetags import strip_all
from .utils import UnionAlias


class Serializer(BaseTransformer):
    ###########
    # helpers #
    ###########

    def embed_condition(self, t):
        if not subclasscheck(t, UnionAlias):
            return t

    ######################
    # transform: codegen #
    ######################

    @extend_super
    @standard_code_generator
    def transform(self, t: type[Model], obj: object, state: State, /):
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


default = Serializer()
serialize = default.transform

default_check = Serializer(validate=True)
serialize_check = default_check.transform
