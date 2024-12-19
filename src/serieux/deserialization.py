from dataclasses import dataclass, fields
from itertools import pairwise
from types import NoneType, UnionType
from typing import Union, get_args, get_origin

from ovld import Code, Dataclass, call_next, extend_super, ovld, recurse

from .transform import CodegenState, Transformer, gensym
from .utils import JSONType, UnionAlias, evaluate_hint


class Tell:
    def __lt__(self, other):
        return self.cost() < other.cost()

    def cost(self):
        return 1


@dataclass(frozen=True)
class TypeTell(Tell):
    t: type

    def gen(self, arg):
        return Code("isinstance($arg, $t)", arg=arg, t=self.t)


@dataclass(frozen=True)
class KeyTell(Tell):
    key: str

    def gen(self, arg):
        return Code("(isinstance($arg, dict) and $k in $arg)", arg=arg, k=self.key)

    def cost(self):
        return 2


class Deserializer(Transformer):
    validate_by_default = True

    #########
    # tells #
    #########

    def tells(self, typ: type[int] | type[str] | type[bool] | type[float]):
        return {TypeTell(typ)}

    def tells(self, dc: type[Dataclass]):
        dc = get_origin(dc) or dc
        return {TypeTell(dict)} | {KeyTell(f.name) for f in fields(dc)}

    ###########
    # codegen #
    ###########

    @extend_super
    def codegen(self, state: CodegenState, x: type[dict], accessor, /):
        kt, vt = get_args(x)
        ktmp, vtmp = gensym("key", "value")
        kx = recurse(state, evaluate_hint(kt), ktmp)
        vx = recurse(state, evaluate_hint(vt), vtmp)
        return Code("{$kx: $vx for $ktmp, $vtmp in $accessor.items()}", locals())

    def codegen(self, state: CodegenState, x: type[list], accessor, /):
        (et,) = get_args(x)
        etmp = gensym("elt")
        ex = recurse(state, evaluate_hint(et), etmp)
        code = Code("[$ex for $etmp in $accessor]", locals())
        return self.guard_codegen(state, list, accessor, code)

    def codegen(self, state: CodegenState, x: type[UnionAlias], accessor, /):
        options = get_args(x)
        tells = [self.tells(o) for o in options]
        for tl1, tl2 in pairwise(tells):
            inter = tl1 & tl2
            tl1 -= inter
            tl2 -= inter

        if sum(not tl for tl in tells) > 1:
            raise Exception("Cannot differentiate the possible union members.")

        options = list(zip(tells, options))
        options.sort(key=lambda x: len(x[0]))

        (_, o1), *rest = options

        code = recurse(state, o1, accessor)
        for tls, opt in rest:
            code = Code(
                "($ocode if $cond else $code)",
                cond=min(tls).gen(accessor),
                code=code,
                ocode=recurse(state, opt, accessor),
            )
        return code

    def codegen(self, state: CodegenState, obj: type[object], accessor, /):
        model = self.model(obj)
        return Code(
            "$cons($[,]parts)",
            cons=model.constructor,
            parts=[
                recurse(
                    state,
                    f.type,
                    Code("$accessor[$fname]", accessor=accessor, fname=f.serialized_name),
                )
                for f in model.fields
            ],
        )

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
            tmp = gensym("tmp")
            dflt = self.default_codegen(state, x, tmp)
            return Code("$tmp if ($tmp := $accessor) is None else $dflt", locals())
        else:
            return accessor

    #########################
    # transform_is_standard #
    #########################

    def standard_pair(self, typ):
        t = get_origin(typ) or typ
        if t is Union or t is UnionType:
            return (type[typ], dict | int | float | str | bool | NoneType)
        elif issubclass(t, (int, float, str, bool, NoneType)):
            return (type[typ], typ)
        elif issubclass(t, list):
            return (type[typ], list)
        else:
            return (type[typ], dict)


default = Deserializer()
deserialize = default.transform


default_check = Deserializer(validate=True)
deserialize_check = default_check.transform
