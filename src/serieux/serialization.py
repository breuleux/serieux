from typing import Any, get_args

from ovld import Code, Def, Lambda, extend_super

from .base import BaseTransformer, standard_code_generator
from .model import Modelizable, model
from .state import State
from .typetags import strip_all
from .utils import UnionAlias


class Serializer(BaseTransformer):
    ######################
    # transform: codegen #
    ######################

    @extend_super
    @standard_code_generator
    def transform(self, t: type[Modelizable], obj: object, state: State, /):
        (t,) = get_args(t)
        t = model(t)
        stmts = []
        for i, f in enumerate(t.fields):
            stmt = Code(
                f"v_{i} = $setter",
                setter=self.subcode(f.type, f"$obj.{f.property_name}", state),
            )
            stmts.append(stmt)
        final = Code(
            "return {$[,]parts}",
            parts=[
                Code(
                    f"$fname: v_{i}",
                    fname=f.serialized_name,
                )
                for i, f in enumerate(t.fields)
            ],
        )
        stmts.append(final)
        return Def(stmts)

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
