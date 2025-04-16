import re
from dataclasses import MISSING, field
from datetime import date, datetime, timedelta
from enum import Enum
from functools import wraps
from itertools import pairwise
from pathlib import Path
from types import NoneType, UnionType
from typing import Any, get_args, get_origin

import yaml
from ovld import (
    Code,
    CodegenInProgress,
    CodegenParameter,
    Def,
    Lambda,
    Medley,
    call_next,
    code_generator,
    keyword_decorator,
    ovld,
    recurse,
)
from ovld.medley import KeepLast, use_combiner
from ovld.types import All

from .ctx import AccessPath, Context
from .exc import SerieuxError, ValidationError, ValidationExceptionGroup
from .features.fromfile import WorkingDirectory
from .instructions import InstructionType, strip_all
from .model import Modelizable, model
from .schema import AnnotatedSchema, Schema
from .tell import tells as get_tells
from .utils import (
    PRIO_DEFAULT,
    PRIO_LAST,
    PRIO_LOW,
    PRIO_TOP,
    UnionAlias,
    clsstring,
)


@keyword_decorator
def code_generator_wrap_error(fn, priority=0):
    @wraps(fn)
    def f(cls, *args, **kwargs):
        result = fn(cls, *args, **kwargs)
        if not result:
            return None
        body = result.create_body(("t", "obj", "ctx"))
        stmts = [
            "try:",
            [body],
            "except $SXE:",
            ["raise"],
            "except Exception as exc:",
            ["raise $VE(exc=exc, ctx=$ctx)"],
        ]
        return Def(stmts, SXE=SerieuxError, VE=ValidationError)

    return code_generator(f, priority=priority)


class BaseImplementation(Medley):
    default_context: Context = field(default_factory=AccessPath)
    validate_serialize: CodegenParameter[bool] = True
    validate_deserialize: CodegenParameter[bool] = True

    def __post_init__(self):
        self._schema_cache = {}

    #######################
    # User-facing methods #
    #######################

    @use_combiner(KeepLast)
    def load(self, t, obj, ctx=None):
        ctx = ctx or self.default_context
        return self.deserialize(t, obj, ctx)

    @use_combiner(KeepLast)
    def dump(self, t, obj, ctx=None, *, dest=None):
        ctx = ctx or self.default_context
        if dest:
            dest = Path(dest)
            ctx = ctx + WorkingDirectory(origin=dest)
        serialized = self.serialize(t, obj, ctx)
        if dest:
            assert dest.suffix == ".yaml"  # TODO: support other formats
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(yaml.safe_dump(serialized))
        else:
            return serialized

    ##################
    # Global helpers #
    ##################

    @classmethod
    def subcode(
        cls, method_name, t, accessor, ctx_t, ctx_expr=Code("$ctx"), after=None, validate=None
    ):
        accessor = accessor if isinstance(accessor, Code) else Code(accessor)
        if validate is None:
            validate = getattr(cls, f"validate_{method_name}")
        method = getattr(cls, method_name)
        if ec := getattr(cls, f"{method_name}_embed_condition")(t):
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
    def serialize_embed_condition(cls, t):
        if t in (int, str, bool, float, NoneType):
            return t

    @ovld(priority=PRIO_LAST)
    def serialize(self, t: type[object], obj: object, ctx: Context, /):
        raise ValidationError(
            f"Cannot serialize object of type '{clsstring(type(obj))}'"
            f" into expected type '{clsstring(t)}'.",
            ctx=ctx,
        )

    @ovld(priority=PRIO_LOW)
    def serialize(self, t: type[InstructionType], obj: object, ctx: Context, /):
        return recurse(t.pushdown(), obj, ctx)

    def serialize(self, obj: object, /):
        return recurse(type(obj), obj, self.default_context)

    def serialize(self, t: type[object], obj: object, /):
        return recurse(t, obj, self.default_context)

    #########################################
    # deserialize: helpers and entry points #
    #########################################

    deserialize_embed_condition = serialize_embed_condition

    @ovld(priority=PRIO_LAST)
    def deserialize(self, t: type[object], obj: object, ctx: Context, /):
        try:
            # Pass through if the object happens to already be the right type
            if isinstance(obj, t):
                return obj
        except TypeError:  # pragma: no cover
            pass
        raise ValidationError(
            f"Cannot deserialize object of type '{clsstring(type(obj))}'"
            f" into expected type '{clsstring(t)}'.",
            ctx=ctx,
        )

    @ovld(priority=PRIO_LOW)
    def deserialize(self, t: type[InstructionType], obj: object, ctx: Context, /):
        return recurse(t.pushdown(), obj, ctx)

    def deserialize(self, t: type[object], obj: object, /):
        return recurse(t, obj, self.default_context)

    ####################################
    # schema: helpers and entry points #
    ####################################

    @ovld(priority=PRIO_TOP)
    def schema(self, t: type[object], ctx: Context, /):
        if t not in self._schema_cache:
            self._schema_cache[t] = holder = Schema(t)
            result = call_next(t, ctx)
            holder.update(result)
        return self._schema_cache[t]

    def schema(self, t: type[object], /):
        return recurse(t, self.default_context)

    @ovld(priority=PRIO_LOW)
    def schema(self, t: type[InstructionType], ctx: Context, /):
        return recurse(t.pushdown(), ctx)

    ################################
    # Implementations: basic types #
    ################################

    for T in (int, str, bool, float, NoneType):

        @code_generator(priority=PRIO_DEFAULT)
        def serialize(cls, t: type[T], obj: T, ctx: Context, /):
            return Lambda(Code("$obj"))

        @code_generator(priority=PRIO_DEFAULT)
        def deserialize(cls, t: type[T], obj: T, ctx: Context, /):
            return Lambda(Code("$obj"))

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[int], ctx: Context, /):
        return {"type": "integer"}

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[float], ctx: Context, /):
        return {"type": "number"}

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[str], ctx: Context, /):
        return {"type": "string"}

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[bool], ctx: Context, /):
        return {"type": "boolean"}

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[NoneType], ctx: Context, /):
        return {"type": "null"}

    ##########################
    # Implementations: lists #
    ##########################

    @classmethod
    def __generic_codegen_list(cls, method, t, obj, ctx):
        (t,) = get_args(t)
        (lt,) = get_args(t) or (object,)
        if hasattr(ctx, "follow"):
            ctx_expr = Code("$ctx.follow($objt, $obj, IDX)", objt=obj)
            return Lambda(
                "[$lbody for IDX, X in enumerate($obj)]",
                lbody=cls.subcode(method, lt, "X", ctx, ctx_expr=ctx_expr),
            )
        else:
            return Lambda("[$lbody for X in $obj]", lbody=cls.subcode(method, lt, "X", ctx))

    @code_generator(priority=PRIO_DEFAULT)
    def serialize(cls, t: type[list], obj: list, ctx: Context, /):
        return cls.__generic_codegen_list("serialize", t, obj, ctx)

    @code_generator(priority=PRIO_DEFAULT)
    def deserialize(cls, t: type[list], obj: list, ctx: Context, /):
        return cls.__generic_codegen_list("deserialize", t, obj, ctx)

    def schema(self, t: type[list], ctx: Context, /):
        (lt,) = get_args(t)
        return {"type": "array", "items": recurse(lt, ctx)}

    ##########################
    # Implementations: dicts #
    ##########################

    @classmethod
    def __generic_codegen_dict(cls, method, t: type[dict], obj: dict, ctx: Context, /):
        (t,) = get_args(t)
        kt, vt = get_args(t) or (object, object)
        ctx_expr = (
            Code("$ctx.follow($objt, $obj, K)", objt=obj)
            if hasattr(ctx, "follow")
            else Code("$ctx")
        )
        return Lambda(
            "{$kbody: $vbody for K, V in $obj.items()}",
            kbody=cls.subcode(method, kt, "K", ctx, ctx_expr=ctx_expr),
            vbody=cls.subcode(method, vt, "V", ctx, ctx_expr=ctx_expr),
        )

    @code_generator(priority=PRIO_DEFAULT)
    def serialize(cls, t: type[dict], obj: dict, ctx: Context, /):
        return cls.__generic_codegen_dict("serialize", t, obj, ctx)

    @code_generator(priority=PRIO_DEFAULT)
    def deserialize(cls, t: type[dict], obj: dict, ctx: Context, /):
        return cls.__generic_codegen_dict("deserialize", t, obj, ctx)

    def schema(self, t: type[dict], ctx: Context, /):
        kt, vt = get_args(t)
        return {"type": "object", "additionalProperties": recurse(vt, ctx)}

    ################################
    # Implementations: Modelizable #
    ################################

    @code_generator_wrap_error(priority=PRIO_DEFAULT)
    def serialize(cls, t: type[Modelizable], obj: object, ctx: Context, /):
        (t,) = get_args(t)
        t = model(t)
        if not t.accepts(obj):
            return None
        stmts = []
        follow = hasattr(ctx, "follow")
        for i, f in enumerate(t.fields):
            if f.property_name is None:
                raise ValidationError(
                    f"Cannot serialize '{clsstring(t)}' because its model does not specify how to serialize property '{f.name}'"
                )
            ctx_expr = (
                Code("$ctx.follow($objt, $obj, $fld)", objt=obj, fld=f.name)
                if follow
                else Code("$ctx")
            )
            stmt = Code(
                f"v_{i} = $setter",
                setter=cls.subcode(
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
        return Def(stmts, VE=ValidationError, VEG=ValidationExceptionGroup)

    @code_generator_wrap_error(priority=PRIO_DEFAULT)
    def deserialize(cls, t: type[Modelizable], obj: dict, ctx: Context, /):
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
            processed = cls.subcode(
                "deserialize",
                f.type,
                Code("$obj[$pname]", pname=f.serialized_name),
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
                    pname=f.serialized_name,
                    processed=processed,
                )
            elif f.default_factory is not MISSING:
                expr = Code(
                    "($processed) if $pname in $obj else $dflt()",
                    dflt=f.default_factory,
                    pname=f.serialized_name,
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
        return Def(stmts, VE=ValidationError, VEG=ValidationExceptionGroup)

    @ovld(priority=PRIO_DEFAULT)
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

    @code_generator(priority=PRIO_DEFAULT)
    def serialize(cls, t: type[UnionAlias], obj: Any, ctx: Context, /):
        (t,) = get_args(t)
        o1, *rest = get_args(t)
        code = cls.subcode("serialize", o1, "$obj", ctx, validate=False)
        for opt in rest:
            code = Code(
                "$ocode if isinstance($obj, $sopt) else $code",
                sopt=strip_all(opt),
                ocode=cls.subcode("serialize", opt, "$obj", ctx, validate=False),
                code=code,
            )
        return Lambda(code)

    @code_generator(priority=PRIO_DEFAULT)
    def deserialize(cls, t: type[UnionAlias] | type[UnionType], obj: Any, ctx: Context, /):
        (t,) = get_args(t)
        options = get_args(t)
        tells = [get_tells(o) for o in options]
        for tl1, tl2 in pairwise(tells):
            inter = tl1 & tl2
            tl1 -= inter
            tl2 -= inter

        if sum(not tl for tl in tells) > 1:
            raise Exception(f"Cannot differentiate the possible union members in type '{t}'")

        options = list(zip(tells, options))
        options.sort(key=lambda x: len(x[0]))

        (_, o1), *rest = options

        code = cls.subcode("deserialize", o1, "$obj", ctx)
        for tls, opt in rest:
            code = Code(
                "($ocode if $cond else $code)",
                cond=min(tls).gen(Code("$obj")),
                code=code,
                ocode=cls.subcode("deserialize", opt, "$obj", ctx),
            )
        return Lambda(code)

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[UnionAlias], ctx: Context, /):
        options = get_args(t)
        return {"oneOf": [recurse(opt, ctx) for opt in options]}

    ##########################
    # Implementations: Enums #
    ##########################

    @code_generator_wrap_error(priority=PRIO_DEFAULT)
    def serialize(self, t: type[Enum], obj: Enum, ctx: Context, /):
        return Lambda(Code("$obj.value"))

    @code_generator_wrap_error(priority=PRIO_DEFAULT)
    def deserialize(self, t: type[Enum], obj: Any, ctx: Context, /):
        (t,) = get_args(t)
        return Lambda(Code("$t($obj)", t=t))

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[Enum], ctx: Context, /):
        return {"enum": [e.value for e in t]}

    ##########################
    # Implementations: Dates #
    ##########################

    @code_generator_wrap_error(priority=PRIO_DEFAULT)
    def serialize(self, t: type[date] | type[datetime], obj: date | datetime, ctx: Context, /):
        return Lambda(Code("$obj.isoformat()"))

    @code_generator_wrap_error(priority=PRIO_DEFAULT)
    def deserialize(self, t: type[date] | type[datetime], obj: str, ctx: Context, /):
        (t,) = get_args(t)
        return Lambda(Code("$t.fromisoformat($obj)", t=t))

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[date], ctx: Context, /):
        return {"type": "string", "format": "date"}

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[datetime], ctx: Context, /):
        return {"type": "string", "format": "date-time"}

    ##############################
    # Implementations: timedelta #
    ##############################

    @ovld(priority=PRIO_DEFAULT)
    def serialize(self, t: type[timedelta], obj: timedelta, ctx: Context):
        """Serialize timedelta as Xs (seconds) or Xus (microseconds)."""
        seconds = int(obj.total_seconds())
        if obj.microseconds:
            return f"{seconds}{obj.microseconds:06}us"
        else:
            return f"{seconds}s"

    @ovld(priority=PRIO_DEFAULT)
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
            raise ValidationError("timedelta representation must end with a unit", ctx=ctx)
        for i in range(len(parts) // 2):
            n = parts[i * 2]
            unit = parts[i * 2 + 1].strip()
            if unit not in units:
                raise ValidationError(f"'{unit}' is not a valid timedelta unit", ctx=ctx)
            try:
                kw[units[unit]] = float(n)
            except ValueError:
                raise ValidationError(f"Could not convert '{n}' ({units[unit]}) to float", ctx=ctx)
        return sign * timedelta(**kw)

    @ovld(priority=PRIO_DEFAULT)
    def schema(self, t: type[timedelta], ctx: Context, /):
        return {
            "type": "string",
            "pattern": r"^[+-]?(\d+[dhms]|\d+ms|\d+us)+$",
        }
