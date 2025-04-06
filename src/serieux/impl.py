import re
from dataclasses import MISSING
from datetime import date, datetime, timedelta
from enum import Enum
from itertools import pairwise
from types import NoneType, UnionType
from typing import Any, get_args, get_origin

from ovld import (
    Code,
    CodegenInProgress,
    CodegenParameter,
    Def,
    Lambda,
    Medley,
    call_next,
    code_generator,
    ovld,
    recurse,
)
from ovld.types import All

from .ctx import Context, empty
from .exc import ValidationError
from .model import Modelizable, model
from .schema import AnnotatedSchema, Schema
from .tell import tells as get_tells
from .typetags import TaggedType, strip_all
from .utils import UnionAlias, clsstring


class BaseImplementation(Medley):
    validate_serialize: CodegenParameter[bool] = True
    validate_deserialize: CodegenParameter[bool] = True

    def __post_init__(self):
        self._schema_cache = {}

    ##################
    # Global helpers #
    ##################

    @classmethod
    def subcode(
        self, method_name, t, accessor, ctx_t, ctx_expr=Code("$ctx"), after=None, validate=None
    ):
        accessor = accessor if isinstance(accessor, Code) else Code(accessor)
        if validate is None:
            validate = getattr(self, f"validate_{method_name}")
        method = getattr(self, method_name)
        if ec := getattr(self, f"{method_name}_embed_condition")(t):
            ec = All[ec]
        if ec is not None:
            try:
                fn = method.resolve(type[t], ec, ctx_t, after=after)
                cg = getattr(fn, "__codegen__", None)
                if cg:
                    body = cg.create_expression([None, t, accessor, ctx_expr])
                    ot = get_origin(t) or t
                    if not validate:
                        return Code(body)
                    else:
                        return Code(
                            "$body if isinstance($accessor, $t) else $recurse($self, $t, $accessor, $ctx_expr)",
                            body=Code(body),
                            accessor=accessor,
                            t=ot,
                            recurse=method,
                            ctx_expr=ctx_expr,
                        )
            except (CodegenInProgress, ValueError):  # pragma: no cover
                # This is important if we are going to inline recursively
                # a type that refers to itself down the line.
                # We currently never do that.
                pass
        return Code(
            "$recurse($self, $t, $accessor, $ctx_expr)",
            t=t,
            accessor=accessor,
            recurse=method,
            ctx_expr=ctx_expr,
        )

    ########################################
    # serialize:  helpers and entry points #
    ########################################

    @classmethod
    def serialize_embed_condition(self, t):
        if t in (int, str, bool, float, NoneType):
            return t

    @ovld(priority=-100)
    def serialize(self, t: type[object], obj: object, ctx: Context, /):
        raise ValidationError(
            f"Cannot serialize object of type '{clsstring(type(obj))}'"
            f" into expected type '{clsstring(t)}'.",
            ctx=ctx,
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

    @ovld(priority=-100)
    def deserialize(self, t: type[object], obj: object, ctx: Context, /):
        raise ValidationError(
            f"Cannot deserialize object of type '{clsstring(type(obj))}'"
            f" into expected type '{clsstring(t)}'.",
            ctx=ctx,
        )

    @ovld(priority=-1)
    def deserialize(self, t: type[TaggedType], obj: object, ctx: Context, /):
        return recurse(t.pushdown(), obj, ctx)

    def deserialize(self, obj: object, /):
        return recurse(object, obj, empty)

    def deserialize(self, t: type[object], obj: object, /):
        return recurse(t, obj, empty)

    ####################################
    # schema: helpers and entry points #
    ####################################

    @ovld(priority=1000)
    def schema(self, t: type[object], ctx: Context, /):
        t = model(t)
        if t not in self._schema_cache:
            self._schema_cache[t] = holder = Schema(t)
            result = call_next(t, ctx)
            holder.update(result)
        return self._schema_cache[t]

    def schema(self, t: type[object], /):
        return recurse(t, empty)

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

    def schema(self, t: type[int], ctx: Context, /):
        return {"type": "integer"}

    def schema(self, t: type[float], ctx: Context, /):
        return {"type": "number"}

    def schema(self, t: type[str], ctx: Context, /):
        return {"type": "string"}

    def schema(self, t: type[bool], ctx: Context, /):
        return {"type": "boolean"}

    def schema(self, t: type[NoneType], ctx: Context, /):
        return {"type": "null"}

    ##########################
    # Implementations: lists #
    ##########################

    @classmethod
    def __generic_codegen_list(self, method, t, obj, ctx):
        (t,) = get_args(t)
        (lt,) = get_args(t) or (object,)
        if hasattr(ctx, "follow"):
            ctx_expr = Code("$ctx.follow($objt, $obj, IDX)", objt=obj)
            return Lambda(
                "[$lbody for IDX, X in enumerate($obj)]",
                lbody=self.subcode(method, lt, "X", ctx, ctx_expr=ctx_expr),
            )
        else:
            return Lambda("[$lbody for X in $obj]", lbody=self.subcode(method, lt, "X", ctx))

    @code_generator
    def serialize(self, t: type[list], obj: list, ctx: Context, /):
        return self.__generic_codegen_list("serialize", t, obj, ctx)

    @code_generator
    def deserialize(self, t: type[list], obj: list, ctx: Context, /):
        return self.__generic_codegen_list("deserialize", t, obj, ctx)

    def schema(self, t: type[list], ctx: Context, /):
        (lt,) = get_args(t)
        return {"type": "array", "items": recurse(lt, ctx)}

    ##########################
    # Implementations: dicts #
    ##########################

    @classmethod
    def __generic_codegen_dict(self, method, t: type[dict], obj: dict, ctx: Context, /):
        (t,) = get_args(t)
        kt, vt = get_args(t) or (object, object)
        ctx_expr = (
            Code("$ctx.follow($objt, $obj, K)", objt=obj)
            if hasattr(ctx, "follow")
            else Code("$ctx")
        )
        return Lambda(
            "{$kbody: $vbody for K, V in $obj.items()}",
            kbody=self.subcode(method, kt, "K", ctx, ctx_expr=ctx_expr),
            vbody=self.subcode(method, vt, "V", ctx, ctx_expr=ctx_expr),
        )

    @code_generator
    def serialize(self, t: type[dict], obj: dict, ctx: Context, /):
        return self.__generic_codegen_dict("serialize", t, obj, ctx)

    @code_generator
    def deserialize(self, t: type[dict], obj: dict, ctx: Context, /):
        return self.__generic_codegen_dict("deserialize", t, obj, ctx)

    def schema(self, t: type[dict], ctx: Context, /):
        kt, vt = get_args(t)
        return {"type": "object", "additionalProperties": recurse(vt, ctx)}

    ################################
    # Implementations: Modelizable #
    ################################

    @code_generator
    def serialize(self, t: type[Modelizable], obj: object, ctx: Context, /):
        (t,) = get_args(t)
        t = model(t)
        if not t.accepts(obj):
            return None
        stmts = []
        follow = hasattr(ctx, "follow")
        for i, f in enumerate(t.fields):
            ctx_expr = (
                Code("$ctx.follow($objt, $obj, $fld)", objt=obj, fld=f.name)
                if follow
                else Code("$ctx")
            )
            stmt = Code(
                f"v_{i} = $setter",
                setter=self.subcode(
                    "serialize", f.type, f"$obj.{f.property_name}", ctx, ctx_expr=ctx_expr
                ),
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
        stmts = [
            "try:",
            stmts,
            "except $ValidationError:",
            ["raise"],
            "except Exception as exc:",
            ["raise $ValidationError(exc=exc, ctx=$ctx)"],
        ]
        return Def(stmts, ValidationError=ValidationError)

    @code_generator
    def deserialize(self, t: type[Modelizable], obj: dict, ctx: Context, /):
        (t,) = get_args(t)
        t = model(t)
        follow = hasattr(ctx, "follow")
        stmts = []
        args = []
        for i, f in enumerate(t.fields):
            ctx_expr = (
                Code("$ctx.follow($objt, $obj, $fld)", objt=obj, fld=f.name)
                if follow
                else Code("$ctx")
            )
            processed = self.subcode(
                "deserialize",
                f.type,
                Code("$obj[$pname]", pname=f.property_name),
                ctx,
                ctx_expr=ctx_expr,
            )
            if f.metavar:
                expr = Code(f.metavar)
            elif f.required:
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

        stmts = [
            "try:",
            stmts,
            "except $ValidationError:",
            ["raise"],
            "except Exception as exc:",
            ["raise $ValidationError(exc=exc, ctx=$ctx)"],
        ]
        return Def(stmts, ValidationError=ValidationError)

    def schema(self, t: type[Modelizable], ctx: Context, /):
        t = model(t)
        properties = {}
        required = []

        for f in t.fields:
            fsch = recurse(f.type, ctx)
            extra = {}
            if f.description:
                extra["description"] = f.description
            if f.default is not MISSING:
                extra["default"] = f.default
            fsch = fsch if not f.description else AnnotatedSchema(fsch, **extra)
            properties[f.property_name] = fsch
            if f.required:
                required.append(f.property_name)

        return {"type": "object", "properties": properties, "required": required}

    ###########################
    # Implementations: Unions #
    ###########################

    @code_generator
    def serialize(self, t: type[UnionAlias], obj: Any, ctx: Context, /):
        (t,) = get_args(t)
        o1, *rest = get_args(t)
        code = self.subcode("serialize", o1, "$obj", ctx, validate=False)
        for opt in rest:
            code = Code(
                "$ocode if isinstance($obj, $sopt) else $code",
                sopt=strip_all(opt),
                ocode=self.subcode("serialize", opt, "$obj", ctx, validate=False),
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

    def schema(self, t: type[UnionAlias], ctx: Context, /):
        options = get_args(t)
        return {"oneOf": [recurse(opt, ctx) for opt in options]}

    ##########################
    # Implementations: Enums #
    ##########################

    @code_generator
    def serialize(self, t: type[Enum], obj: Enum, ctx: Context, /):
        return Lambda(Code("$obj.value"))

    @code_generator
    def deserialize(self, t: type[Enum], obj: Any, ctx: Context, /):
        (t,) = get_args(t)
        return Lambda(Code("$t($obj)", t=t))

    def schema(self, t: type[Enum], ctx: Context, /):
        return {"enum": [e.value for e in t]}

    ##########################
    # Implementations: Dates #
    ##########################

    @code_generator
    def serialize(self, t: type[date] | type[datetime], obj: date | datetime, ctx: Context, /):
        return Lambda(Code("$obj.isoformat()"))

    @code_generator
    def deserialize(self, t: type[date] | type[datetime], obj: str, ctx: Context, /):
        (t,) = get_args(t)
        return Lambda(Code("$t.fromisoformat($obj)", t=t))

    def schema(self, t: type[date], ctx: Context, /):
        return {"type": "string", "format": "date"}

    def schema(self, t: type[datetime], ctx: Context, /):
        return {"type": "string", "format": "date-time"}

    ##############################
    # Implementations: timedelta #
    ##############################

    def serialize(self, t: type[timedelta], obj: timedelta, ctx: Context):
        """Serialize timedelta as Xs (seconds) or Xus (microseconds)."""
        seconds = int(obj.total_seconds())
        if obj.microseconds:
            return f"{seconds}{obj.microseconds:06}us"
        else:
            return f"{seconds}s"

    def deserialize(self, t: type[timedelta], obj: str, ctx: Context):
        """Deserialize a combination of days, hours, etc. as a timedelta."""
        units = {
            "d": "days",
            "h": "hours",
            "m": "minutes",
            "s": "seconds",
            "ms": "milliseconds",
            "us": "microseconds",
        }
        sign = 1
        if obj.startswith("-"):
            obj = obj[1:]
            sign = -1
        kw = {}
        parts = re.split(string=obj, pattern="([a-z ]+)")
        if parts[-1] != "":
            raise TypeError("timedelta representation must end with a unit")
        for i in range(len(parts) // 2):
            n = parts[i * 2]
            unit = parts[i * 2 + 1].strip()
            if unit not in units:
                raise TypeError(f"'{unit}' is not a valid timedelta unit")
            try:
                kw[units[unit]] = float(n)
            except ValueError as err:
                raise TypeError(f"Could not convert '{n}' ({units[unit]}) to float") from err
        return sign * timedelta(**kw)

    def schema(self, t: type[timedelta], ctx: Context, /):
        return {
            "type": "string",
            "pattern": r"^[+-]?(\d+[dhms]|\d+ms|\d+us)+$",
        }
