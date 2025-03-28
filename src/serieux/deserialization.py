from dataclasses import MISSING
from itertools import pairwise
from types import UnionType
from typing import Any, get_args

from ovld import Code, Def, Lambda, extend_super

from .base import BaseTransformer, standard_code_generator
from .model import Modelizable, model
from .state import State
from .tell import tells as get_tells
from .utils import UnionAlias


class Deserializer(BaseTransformer):
    ######################
    # transform: codegen #
    ######################

    @extend_super
    @standard_code_generator
    def transform(self, t: type[Modelizable], obj: dict, state: State, /):
        (t,) = get_args(t)
        t = model(t)
        stmts = []
        args = []
        for i, f in enumerate(t.fields):
            processed = self.subcode(f.type, Code("$obj[$pname]", pname=f.property_name), state)
            if f.required:
                expr = processed
            elif f.default is not MISSING:
                expr = Code(
                    "($processed) if $pname in $obj else $dflt",
                    dflt=f.default,
                    pname=f.property_name,
                    processed=processed,
                )
            elif f.default_factory is not MISSING:
                expr = Code(
                    "($processed) if $pname in $obj else $dflt()",
                    dflt=f.default_factory,
                    pname=f.property_name,
                    processed=processed,
                )
            stmt = Code(f"v_{i} = $expr", expr=expr)
            stmts.append(stmt)
            if isinstance(f.argument_name, str):
                arg = f"{f.argument_name}=v_{i}"
            else:
                arg = f"v_{i}"
            args.append(arg)

        final = Code(
            "return $constructor($[,]parts)",
            constructor=t.constructor,
            parts=[Code(a) for a in args],
        )

        stmts.append(final)
        return Def(stmts)

    @standard_code_generator
    def transform(self, t: type[UnionAlias] | type[UnionType], obj: Any, state: State, /):
        (t,) = get_args(t)
        options = get_args(t)
        tells = [get_tells(model(o)) for o in options]
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
