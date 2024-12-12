from dataclasses import fields
from types import NoneType
from typing import get_args, get_origin

from ovld import (
    CodeGen,
    Dataclass,
    OvldPerInstanceBase,
    call_next,
    code_generator,
    ovld,
    recurse,
)

from .exc import ValidationError
from .proxy import TrackingProxy, get_annotations
from .utils import JSONType, NameDatabase, UnionAlias, evaluate_hint

_codegen_template = """
try:
    return {expr}
except Exception as exc:
    return self.serialize_handle_exception($typ, {obj}, exc)
"""


def _compatible(t1, t2):
    if issubclass(t2, TrackingProxy):
        t2 = t2._self_cls
    return issubclass(t2, get_origin(t1) or t1)


class Serializer(OvldPerInstanceBase):
    def __init__(self, validate_serialization=False):
        self.validate_serialization = validate_serialization

    @classmethod
    def ovld_instance_key(cls, validate_serialization=False):
        return (("validate_serialization", validate_serialization),)

    #####################
    # serialize_codegen #
    #####################

    def guard_codegen(self, ndb, typ, accessor, body):
        if not self.validate_serialization:
            return body.replace("$$$", accessor)
        else:
            tmp = ndb.gensym("tmp")
            otyp = get_origin(typ) or typ
            otyp_embed = ndb.stash(typ if typ is otyp else otyp, prefix="T")
            body = body.replace("$$$", tmp)
            dflt = self.default_codegen(ndb, typ, accessor)
            code = f"({body} if isinstance({tmp} := {accessor}, {otyp_embed}) else {dflt})"
            return code

    def default_codegen(
        self, ndb: NameDatabase, typ: type[object], accessor: str
    ):
        t = ndb.stash(typ, prefix="T")
        return f"$recurse(self, {t}, {accessor})"

    @ovld(priority=100)
    def serialize_codegen(
        self, ndb: NameDatabase, typ: type[object], accessor, /
    ):
        if typ in ndb.seen and typ not in (int, str, bool, NoneType):
            return self.default_codegen(ndb, typ, accessor)
        else:
            ndb.seen.add(typ)
            return call_next(ndb, typ, accessor)

    def serialize_codegen(
        self, ndb: NameDatabase, dc: type[Dataclass], accessor, /
    ):
        parts = []
        tsub = {}
        if (origin := get_origin(dc)) is not None:
            tsub = dict(zip(origin.__type_params__, get_args(dc)))
            dc = origin
        for f in fields(dc):
            ftype = evaluate_hint(f.type, ctx=dc, typesub=tsub)
            setter = recurse(ndb, ftype, f"$$$.{f.name}")
            parts.append(f"'{f.name}': {setter}")
        code = "{" + ",".join(parts) + "}"
        return self.guard_codegen(ndb, dc, accessor, code)

    def serialize_codegen(self, ndb: NameDatabase, x: type[dict], accessor, /):
        kt, vt = get_args(x)
        ktmp = ndb.gensym("key")
        vtmp = ndb.gensym("value")
        kx = recurse(ndb, kt, ktmp)
        vx = recurse(ndb, vt, vtmp)
        code = f"{{{kx}: {vx} for {ktmp}, {vtmp} in $$$.items()}}"
        return self.guard_codegen(ndb, x, accessor, code)

    def serialize_codegen(self, ndb: NameDatabase, x: type[list], accessor, /):
        (et,) = get_args(x)
        etmp = ndb.gensym("elt")
        ex = recurse(ndb, et, etmp)
        return self.guard_codegen(ndb, x, accessor, f"[{ex} for {etmp} in $$$]")

    @ovld(priority=1)
    def serialize_codegen(
        self, ndb: NameDatabase, x: type[JSONType[object]], accessor, /
    ):
        if self.validate_serialization:
            return call_next(ndb, x, accessor)
        else:
            return accessor

    def serialize_codegen(
        self,
        ndb: NameDatabase,
        x: type[int] | type[str] | type[bool],
        accessor,
        /,
    ):
        return self.guard_codegen(ndb, x, accessor, "$$$")

    def serialize_codegen(
        self, ndb: NameDatabase, x: type[NoneType], accessor, /
    ):
        if self.validate_serialization:
            tmp = ndb.gensym("tmp")
            return f"({tmp} if ({tmp} := {accessor}) is None else {call_next(ndb, x, tmp)})"
        else:
            return accessor

    def serialize_codegen(
        self, ndb: NameDatabase, x: type[UnionAlias], accessor, /
    ):
        o1, *rest = get_args(x)
        code = recurse(ndb, o1, accessor)
        for opt in rest:
            ocode = recurse(ndb, opt, accessor)
            t = ndb.stash(opt, prefix="T")
            code = f"({ocode} if isinstance({accessor}, {t}) else {code})"
        return code

    def serialize_codegen(
        self, ndb: NameDatabase, x: type[object], accessor, /
    ):
        raise NotImplementedError()

    def make_code(self, typ: type[object], accessor, recurse, toplevel=False):
        ndb = NameDatabase()
        try:
            expr = self.serialize_codegen(ndb, typ, accessor)
        except NotImplementedError:
            return None
        if toplevel:
            code = _codegen_template.format(expr=expr, obj=accessor)
        else:
            code = f"return {expr}"
        return CodeGen(
            code,
            typ=typ,
            recurse=recurse,
            **ndb.vars,
        )

    #############
    # serialize #
    #############

    @code_generator
    def serialize(self, x: object):
        return self.make_code(
            x, "x", self.serialize_sync.__ovld__.dispatch, toplevel=True
        )

    @code_generator
    def serialize(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        if _compatible(t, value):
            return self.make_code(
                t, "value", self.serialize_sync.__ovld__.dispatch, toplevel=True
            )

    def serialize(self, typ, value):
        try:
            return self.serialize_sync(typ, value)
        except Exception as exc:
            self.serialize_handle_exception(typ, value, exc)

    ##################
    # serialize_sync #
    ##################

    @code_generator
    def serialize_sync(self, x: object):
        return self.make_code(x, "x", recurse)

    @code_generator
    def serialize_sync(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        if _compatible(t, value):
            return self.make_code(t, "value", recurse)

    @ovld(priority=10)
    def serialize_sync(self, typ: type[object], value: TrackingProxy):
        try:
            return call_next(typ, value)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(exc=exc, ctx=get_annotations(value))

    @ovld(priority=-1)
    def serialize_sync(self, typ: type[object], value: object):
        tv = type(value)
        if isinstance(value, TrackingProxy):
            tv = tv._self_cls
        raise TypeError(f"No way to serialize {tv} as {typ}")

    ###############################
    # serialize exception handler #
    ###############################

    @ovld(priority=10)
    def serialize_handle_exception(self, typ, value, exc: ValidationError):
        raise

    def serialize_handle_exception(self, typ, value: TrackingProxy, exc):
        raise ValidationError(exc=exc, ctx=value._self_ann)

    def serialize_handle_exception(self, typ, value, exc):
        return self.serialize(typ, TrackingProxy.make(value))


default = Serializer()
serialize = default.serialize

default_check = Serializer(validate_serialization=True)
serialize_check = default_check.serialize
