from itertools import pairwise
from types import UnionType
from typing import Any, get_args

from ovld import Code, Lambda, extend_super

from .base import BaseTransformer, standard_code_generator
from .model import Modell as Model
from .state import State
from .tell import tells as get_tells
from .typetags import make_tag
from .utils import UnionAlias


class Deserializer(BaseTransformer):
    ######################
    # transform: codegen #
    ######################

    @extend_super
    @standard_code_generator
    def transform(self, t: type[Model], obj: dict, state: State, /):
        (t,) = get_args(t)
        return Lambda(
            "$constructor($[,]parts)",
            constructor=t.constructor,
            parts=[
                Code(
                    f"{f.argument_name}=$setter"
                    if isinstance(f.argument_name, str)
                    else "$setter",
                    setter=self.subcode(
                        f.type, Code("$obj[$pname]", pname=f.property_name), state
                    ),
                )
                for f in t.fields
            ],
        )

    @standard_code_generator
    def transform(self, t: type[UnionAlias] | type[UnionType], obj: Any, state: State, /):
        (t,) = get_args(t)
        options = get_args(t)
        tells = [get_tells(o) for o in options]
        for tl1, tl2 in pairwise(tells):
            inter = tl1 & tl2
            tl1 -= inter
            tl2 -= inter

        if sum(not tl for tl in tells) > 1:
            raise Exception("Cannot differentiate the possible union members.")

        options = list(zip(tells, options))
        options.sort(key=lambda x: len(x[0]))

        (_, o1), *rest = options

        code = self.subcode(o1, "$obj", state)
        for tls, opt in rest:
            code = Code(
                "($ocode if $cond else $code)",
                cond=min(tls).gen(Code("$obj")),
                code=code,
                ocode=self.subcode(opt, "$obj", state),
            )
        return Lambda(code)


default = Deserializer(validate=False)
deserialize = default.transform

default_check = Deserializer(validate=True)
deserialize_check = default_check.transform
