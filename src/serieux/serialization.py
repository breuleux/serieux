from dataclasses import fields
from types import NoneType
from typing import get_args, get_origin

from ovld import Code, Dataclass, call_next, extend_super, ovld, recurse

from .transform import CodegenState, Transformer, gensym, standard_code_generator
from .utils import JSONType, UnionAlias, evaluate_hint


class Serializer(Transformer):
    validate_by_default = False

    ###########
    # codegen #
    ###########

    @extend_super
    def codegen(self, state: CodegenState, dc: type[Dataclass], accessor, /):
        tsub = {}
        if (origin := get_origin(dc)) is not None:
            tsub = dict(zip(origin.__type_params__, get_args(dc)))
            dc = origin

        code = Code(
            "{$[,]parts}",
            parts=[
                Code(
                    "$fname: $setter",
                    fname=f.name,
                    setter=recurse(
                        state,
                        evaluate_hint(f.type, ctx=dc, typesub=tsub),
                        Code(f"$accessor.{f.name}", accessor=accessor),
                    ),
                )
                for f in fields(dc)
            ],
        )
        return self.guard_codegen(state, dc, accessor, code)

    def codegen(self, state: CodegenState, x: type[dict], accessor, /):
        kt, vt = get_args(x)
        ktmp, vtmp = gensym("key", "value")
        kx = recurse(state, evaluate_hint(kt), ktmp)
        vx = recurse(state, evaluate_hint(vt), vtmp)
        code = Code("{$kx: $vx for $ktmp, $vtmp in $accessor.items()}", locals())
        return self.guard_codegen(state, x, accessor, code)

    def codegen(self, state: CodegenState, x: type[list], accessor, /):
        (et,) = get_args(x)
        etmp = gensym("elt")
        ex = recurse(state, evaluate_hint(et), etmp)
        code = Code("[$ex for $etmp in $accessor]", locals())
        return self.guard_codegen(state, x, accessor, code)

    @ovld(priority=1)
    def codegen(self, state: CodegenState, x: type[JSONType[object]], accessor, /):
        if self.validate or not self.transform_is_standard(x, True):
            return call_next(state, x, accessor)
        else:
            return accessor

    def codegen(
        self,
        state: CodegenState,
        x: type[int] | type[str] | type[bool] | type[float],
        accessor,
        /,
    ):
        return self.guard_codegen(state, x, accessor, Code("$accessor", accessor=accessor))

    def codegen(self, state: CodegenState, x: type[NoneType], accessor, /):
        if self.validate:
            tmp = gensym()
            dflt = self.default_codegen(state, x, tmp)
            return Code("$tmp if ($tmp := $accessor) is None else $dflt", locals())
        else:
            return accessor

    def codegen(self, state: CodegenState, x: type[UnionAlias], accessor, /):
        o1, *rest = get_args(x)
        code = recurse(state, o1, accessor)
        for opt in rest:
            ocode = recurse(state, opt, accessor)
            code = Code("$ocode if isinstance($accessor, $opt) else $code", locals())
        return code

    def codegen(self, state: CodegenState, x: type[object], accessor, /):
        raise NotImplementedError()

    #################
    # standard_pair #
    #################

    def standard_pair(self, typ):
        return (type[typ], typ)

    #############
    # transform #
    #############

    @extend_super
    @standard_code_generator
    def transform(self, x: object):
        if self.transform_is_standard(x):
            return self.make_code(x, "x", self.transform_sync.__ovld__.dispatch, toplevel=True)

    @ovld(priority=-1)
    def transform(self, x):
        typ = type(x)
        try:
            return self.transform_sync(typ, x)
        except Exception as exc:
            self.handle_exception(typ, x, exc)


default = Serializer()
serialize = default.transform

default_check = Serializer(validate=True)
serialize_check = default_check.transform
