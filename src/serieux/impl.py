from dataclasses import MISSING
from itertools import pairwise
from types import NoneType, UnionType
from typing import Any, get_args, get_origin

from ovld import (
    Code,
    CodegenInProgress,
    Def,
    Lambda,
    Medley,
    code_generator,
    ovld,
    recurse,
)
from ovld.types import All

from .ctx import Context, empty
from .model import Modelizable, model
from .tell import tells as get_tells
from .typetags import TaggedType, strip_all
from .utils import UnionAlias


class BaseImplementation(Medley):
    validate_serialize: bool = True
    validate_deserialize: bool = True

    ##################
    # Global helpers #
    ##################

    @classmethod
    def subcode(self, method, t, accessor, ctx_t, after=None):
        if ec := getattr(self, f"{method}_embed_condition")(t):
            ec = All[ec]
        if ec is not None:
            try:
                fn = getattr(self, method).resolve(type[t], ec, ctx_t, after=after)
                cg = getattr(fn, "__codegen__", None)
                if cg:
                    return self.guard_codegen(
                        method,
                        get_origin(t) or t,
                        accessor,
                        cg.create_expression([None, t, accessor, "$ctx"]),
                    )
            except (CodegenInProgress, ValueError):
                pass
        return getattr(self, f"{method}_default_codegen")(t, accessor)

    @classmethod
    def guard_codegen(self, method, t, accessor, body):
        if not getattr(self, f"validate_{method}"):
            return Code(body)
        else:
            return Code(
                "$body if isinstance($accessor, $t) else $dflt",
                body=Code(body),
                accessor=Code(accessor),
                t=t,
                dflt=getattr(self, f"{method}_default_codegen")(t, accessor),
            )

    ########################################
    # serialize:  helpers and entry points #
    ########################################

    @classmethod
    def serialize_embed_condition(self, t):
        if t in (int, str, bool, float, NoneType):
            return t

    @classmethod
    def serialize_default_codegen(self, t, accessor):
        return Code(
            "$recurse($self, $t, $accessor, $ctx)",
            t=t,
            accessor=accessor if isinstance(accessor, Code) else Code(accessor),
            recurse=self.serialize,
        )

    @ovld(priority=-1)
    def serialize(self, t: type[TaggedType], obj: object, ctx: Context, /):
        return recurse(t.pushdown(), obj, ctx)

    def serialize(self, obj: object, /):
        return recurse(type(obj), obj, empty)

    def serialize(self, t: type[object], obj: object, /):
        return recurse(t, obj, empty)

    #########################################
    # deserialize: helpers and entry points #
    #########################################

    deserialize_embed_condition = serialize_embed_condition

    @classmethod
    def deserialize_default_codegen(self, t, accessor):
        return Code(
            "$recurse($self, $t, $accessor, $ctx)",
            t=t,
            accessor=accessor if isinstance(accessor, Code) else Code(accessor),
            recurse=self.deserialize,
        )

    @ovld(priority=-1)
    def deserialize(self, t: type[TaggedType], obj: object, ctx: Context, /):
        return recurse(t.pushdown(), obj, ctx)

    def deserialize(self, obj: object, /):
        return recurse(object, obj, empty)

    def deserialize(self, t: type[object], obj: object, /):
        return recurse(t, obj, empty)

    ################################
    # Implementations: basic types #
    ################################

    for T in (int, str, bool, float, NoneType):

        @code_generator
        def serialize(self, t: type[T], obj: T, ctx: Context, /):
            return Lambda(Code("$obj"))

        @code_generator
        def deserialize(self, t: type[T], obj: T, ctx: Context, /):
            return Lambda(Code("$obj"))

    ##########################
    # Implementations: lists #
    ##########################

    @classmethod
    def __generic_codegen_list(self, method, t, obj, ctx):
        (t,) = get_args(t)
        (lt,) = get_args(t)
        return Lambda("[$lbody for X in $obj]", lbody=self.subcode(method, lt, "X", ctx))

    @code_generator
    def serialize(self, t: type[list], obj: list, ctx: Context, /):
        return self.__generic_codegen_list("serialize", t, obj, ctx)

    @code_generator
    def deserialize(self, t: type[list], obj: list, ctx: Context, /):
        return self.__generic_codegen_list("deserialize", t, obj, ctx)

    ##########################
    # Implementations: dicts #
    ##########################

    @classmethod
    def __generic_codegen_dict(self, method, t: type[dict], obj: dict, ctx: Context, /):
        (t,) = get_args(t)
        kt, vt = get_args(t)
        return Lambda(
            "{$kbody: $vbody for K, V in $obj.items()}",
            kbody=self.subcode(method, kt, "K", ctx),
            vbody=self.subcode(method, vt, "V", ctx),
        )

    @code_generator
    def serialize(self, t: type[dict], obj: dict, ctx: Context, /):
        return self.__generic_codegen_dict("serialize", t, obj, ctx)

    @code_generator
    def deserialize(self, t: type[dict], obj: dict, ctx: Context, /):
        return self.__generic_codegen_dict("deserialize", t, obj, ctx)

    ################################
    # Implementations: Modelizable #
    ################################

    @code_generator
    def serialize(self, t: type[Modelizable], obj: object, ctx: Context, /):
        (t,) = get_args(t)
        t = model(t)
        stmts = []
        for i, f in enumerate(t.fields):
            stmt = Code(
                f"v_{i} = $setter",
                setter=self.subcode("serialize", f.type, f"$obj.{f.property_name}", ctx),
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

    @code_generator
    def deserialize(self, t: type[Modelizable], obj: dict, ctx: Context, /):
        (t,) = get_args(t)
        t = model(t)
        stmts = []
        args = []
        for i, f in enumerate(t.fields):
            processed = self.subcode(
                "deserialize", f.type, Code("$obj[$pname]", pname=f.property_name), ctx
            )
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

    ###########################
    # Implementations: Unions #
    ###########################

    @code_generator
    def serialize(self, t: type[UnionAlias], obj: Any, ctx: Context, /):
        (t,) = get_args(t)
        o1, *rest = get_args(t)
        code = self.subcode("serialize", o1, "$obj", ctx)
        for opt in rest:
            code = Code(
                "$ocode if isinstance($obj, $sopt) else $code",
                sopt=strip_all(opt),
                ocode=self.subcode("serialize", opt, "$obj", ctx),
                code=code,
            )
        return Lambda(code)

    @code_generator
    def deserialize(self, t: type[UnionAlias] | type[UnionType], obj: Any, ctx: Context, /):
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

        code = self.subcode("deserialize", o1, "$obj", ctx)
        for tls, opt in rest:
            code = Code(
                "($ocode if $cond else $code)",
                cond=min(tls).gen(Code("$obj")),
                code=code,
                ocode=self.subcode("deserialize", opt, "$obj", ctx),
            )
        return Lambda(code)


default_implementation = BaseImplementation(
    validate_serialize=True,
    validate_deserialize=True,
)
serialize = default_implementation.serialize
deserialize = default_implementation.deserialize
