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


def standard_code_generator(fn):
    fn.standard_codegen = True
    return code_generator(fn)


_codegen_template = """
try:
    return {expr}
except Exception as exc:
    return self.handle_exception($typ, {obj}, exc)
"""


def _compatible(t1, t2):
    if issubclass(t2, TrackingProxy):
        t2 = t2._self_cls
    return issubclass(t2, get_origin(t1) or t1)


class Serializer(OvldPerInstanceBase):
    def __init__(self, validate=False):
        self.validate = validate

    @classmethod
    def ovld_instance_key(cls, validate=False):
        return (("this", cls), ("validate", validate))

    ###########
    # codegen #
    ###########

    def guard_codegen(self, ndb, typ, accessor, body):
        if not self.validate:
            return body.replace("$$$", accessor)
        else:
            tmp = ndb.gensym("tmp")
            otyp = get_origin(typ) or typ
            otyp_embed = ndb.stash(typ if typ is otyp else otyp, prefix="T")
            body = body.replace("$$$", tmp)
            dflt = self.default_codegen(ndb, typ, accessor)
            code = f"({body} if isinstance({tmp} := {accessor}, {otyp_embed}) else {dflt})"
            return code

    def default_codegen(self, ndb: NameDatabase, typ: type[object], accessor: str):
        t = ndb.stash(typ, prefix="T")
        return f"$recurse(self, {t}, {accessor})"

    @ovld(priority=100)
    def codegen(self, ndb: NameDatabase, typ: type[object], accessor, /):
        if typ in ndb.seen and typ not in (int, str, bool, NoneType):
            return self.default_codegen(ndb, typ, accessor)
        elif not ndb.seen or self.transform_is_standard(typ):
            # * ndb.seen is empty for the top level generation, and we always proceed.
            # * Otherwise, we are generating code recursively for subfields, but
            #   we only do this if the main transform_sync method is the standard
            #   code generation method.
            ndb.seen.add(typ)
            return call_next(ndb, typ, accessor)
        else:
            return self.default_codegen(ndb, typ, accessor)

    def codegen(self, ndb: NameDatabase, dc: type[Dataclass], accessor, /):
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

    def codegen(self, ndb: NameDatabase, x: type[dict], accessor, /):
        kt, vt = get_args(x)
        ktmp = ndb.gensym("key")
        vtmp = ndb.gensym("value")
        kx = recurse(ndb, kt, ktmp)
        vx = recurse(ndb, vt, vtmp)
        code = f"{{{kx}: {vx} for {ktmp}, {vtmp} in $$$.items()}}"
        return self.guard_codegen(ndb, x, accessor, code)

    def codegen(self, ndb: NameDatabase, x: type[list], accessor, /):
        (et,) = get_args(x)
        etmp = ndb.gensym("elt")
        ex = recurse(ndb, et, etmp)
        return self.guard_codegen(ndb, x, accessor, f"[{ex} for {etmp} in $$$]")

    @ovld(priority=1)
    def codegen(self, ndb: NameDatabase, x: type[JSONType[object]], accessor, /):
        if self.validate or not self.transform_is_standard(x, True):
            return call_next(ndb, x, accessor)
        else:
            return accessor

    def codegen(
        self,
        ndb: NameDatabase,
        x: type[int] | type[str] | type[bool] | type[float],
        accessor,
        /,
    ):
        return self.guard_codegen(ndb, x, accessor, "$$$")

    def codegen(self, ndb: NameDatabase, x: type[NoneType], accessor, /):
        if self.validate:
            tmp = ndb.gensym("tmp")
            return f"({tmp} if ({tmp} := {accessor}) is None else {self.default_codegen(ndb, x, tmp)})"
        else:
            return accessor

    def codegen(self, ndb: NameDatabase, x: type[UnionAlias], accessor, /):
        o1, *rest = get_args(x)
        code = recurse(ndb, o1, accessor)
        for opt in rest:
            ocode = recurse(ndb, opt, accessor)
            t = ndb.stash(opt, prefix="T")
            code = f"({ocode} if isinstance({accessor}, {t}) else {code})"
        return code

    def codegen(self, ndb: NameDatabase, x: type[object], accessor, /):
        raise NotImplementedError()

    def make_code(self, typ: type[object], accessor, recurse, toplevel=False):
        ndb = NameDatabase()
        try:
            expr = self.codegen(ndb, typ, accessor)
        except NotImplementedError:
            return None
        if toplevel:
            code = _codegen_template.format(expr=expr, obj=accessor)
        else:
            code = f"return {expr}"
        return CodeGen(code, typ=typ, recurse=recurse, **ndb.vars)

    #############
    # transform #
    #############

    @standard_code_generator
    def transform(self, x: object):
        if self.transform_is_standard(x):
            return self.make_code(x, "x", self.transform_sync.__ovld__.dispatch, toplevel=True)

    @standard_code_generator
    def transform(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        if _compatible(t, value) and self.transform_is_standard(t):
            return self.make_code(t, "value", self.transform_sync.__ovld__.dispatch, toplevel=True)

    @ovld(priority=-1)
    def transform(self, x):
        typ = type(x)
        try:
            return self.transform_sync(typ, x)
        except Exception as exc:
            self.handle_exception(typ, x, exc)

    @ovld(priority=-1)
    def transform(self, typ, value):
        try:
            return self.transform_sync(typ, value)
        except Exception as exc:
            self.handle_exception(typ, value, exc)

    #########################
    # transform_is_standard #
    #########################

    def transform_is_standard(self, typ, recursive=False):
        """Return whether transform_sync::(type[typ], typ) is standard.

        Codegen for standard implementations can be nested.
        """
        resolved = self.transform_sync.map.mro((type[typ], typ), specialize=False)
        rval = (
            resolved
            and resolved[0]
            and getattr(resolved[0][0].base_handler, "standard_codegen", False)
        )
        if rval and recursive:
            return rval and all(
                self.transform_is_standard(arg, recursive=True) for arg in get_args(typ)
            )
        else:
            return rval

    ##################
    # transform_sync #
    ##################

    @ovld
    @standard_code_generator
    def transform_sync(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        if _compatible(t, value):
            return self.make_code(t, "value", recurse)

    @ovld(priority=10)
    def transform_sync(self, typ: type[object], value: TrackingProxy):
        try:
            return call_next(typ, value)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(exc=exc, ctx=get_annotations(value))

    @ovld(priority=-1)
    def transform_sync(self, typ: type[object], value: object):
        tv = type(value)
        if isinstance(value, TrackingProxy):
            tv = tv._self_cls
        raise TypeError(f"No way to transform {tv} as {typ}")

    #####################
    # exception handler #
    #####################

    @ovld(priority=10)
    def handle_exception(self, typ, value, exc: ValidationError):
        raise

    def handle_exception(self, typ, value: TrackingProxy, exc):
        raise ValidationError(exc=exc, ctx=value._self_ann)

    def handle_exception(self, typ, value, exc):
        return self.transform(typ, TrackingProxy.make(value))


default = Serializer()
serialize = default.transform

default_check = Serializer(validate=True)
serialize_check = default_check.transform
