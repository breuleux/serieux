from dataclasses import fields
from types import NoneType
from typing import get_args, get_origin

from ovld import (
    CodeGen,
    Dataclass,
    OvldPerInstanceBase,
    call_next,
    ovld,
    recurse,
)

from .exc import ValidationError
from .proxy import TrackingProxy, get_annotations
from .serialization import _compatible, standard_code_generator
from .utils import JSONType, NameDatabase, evaluate_hint

_codegen_template = """
try:
    return {expr}
except Exception as exc:
    return self.deserialize_handle_exception($typ, {obj}, exc)
"""


def _compatible(t1, t2):
    if issubclass(t2, TrackingProxy):
        t2 = t2._self_cls
    return issubclass(t2, t1)


class Deserializer(OvldPerInstanceBase):
    def __init__(self, validate_deserialization=True):
        self.validate_deserialization = validate_deserialization

    @classmethod
    def ovld_instance_key(cls, validate_deserialization=True):
        return (("this", cls), ("validate_deserialization", validate_deserialization))

    #######################
    # deserialize_codegen #
    #######################

    def guard_codegen(self, ndb, typ, accessor, body):
        if not self.validate_deserialization:
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
    def deserialize_codegen(self, ndb: NameDatabase, typ: type[object], accessor, /):
        if (ndb.seen and not ndb.nest) or (
            typ in ndb.seen and typ not in (int, str, bool, NoneType)
        ):
            return self.default_codegen(ndb, typ, accessor)
        elif not ndb.seen or self.deserialize_is_standard(typ):
            # * ndb.seen is empty for the top level generation, and we always proceed.
            # * Otherwise, we are generating code recursively for subfields, but
            #   we only do this if the main serialize_sync method is the standard
            #   code generation method.
            ndb.seen.add(typ)
            return call_next(ndb, typ, accessor)
        else:
            return self.default_codegen(ndb, typ, accessor)

    def deserialize_codegen(self, ndb: NameDatabase, dc: type[Dataclass], accessor, /):
        parts = []
        cons = ndb.stash(dc, prefix="T")
        for f in fields(dc):
            ftype = evaluate_hint(f.type, ctx=dc)
            setter = recurse(ndb, ftype, f"{accessor}['{f.name}']")
            parts.append(setter)
        return f"{cons}(" + ",".join(parts) + ")"

    def deserialize_codegen(self, ndb: NameDatabase, x: type[dict], accessor, /):
        kt, vt = get_args(x)
        kt = evaluate_hint(kt)
        vt = evaluate_hint(vt)
        ktmp = ndb.gensym("key")
        vtmp = ndb.gensym("value")
        kx = recurse(ndb, kt, ktmp)
        vx = recurse(ndb, vt, vtmp)
        return f"{{{kx}: {vx} for {ktmp}, {vtmp} in {accessor}.items()}}"

    def deserialize_codegen(self, ndb: NameDatabase, x: type[list], accessor, /):
        (et,) = get_args(x)
        et = evaluate_hint(et)
        etmp = ndb.gensym("elt")
        ex = recurse(ndb, et, etmp)
        # TODO: check that it is a list, because this will accidentally work with dicts
        return f"[{ex} for {etmp} in {accessor}]"

    @ovld(priority=1)
    def deserialize_codegen(self, ndb: NameDatabase, x: type[JSONType[object]], accessor, /):
        if self.validate_deserialization or not self.deserialize_is_standard(x, True):
            return call_next(ndb, x, accessor)
        else:
            return accessor

    def deserialize_codegen(
        self,
        ndb: NameDatabase,
        x: type[int] | type[str] | type[bool] | type[float],
        accessor,
        /,
    ):
        return self.guard_codegen(ndb, x, accessor, "$$$")

    def deserialize_codegen(self, ndb: NameDatabase, x: type[NoneType], accessor, /):
        if self.validate_deserialization:
            tmp = ndb.gensym("tmp")
            return f"({tmp} if ({tmp} := {accessor}) is None else {self.default_codegen(ndb, x, tmp)})"
        else:
            return accessor

    def make_code(self, typ: type[object], accessor, recurse, toplevel=False, nest=True):
        ndb = NameDatabase(nest=nest)
        try:
            expr = self.deserialize_codegen(ndb, typ, accessor)
        except NotImplementedError:
            return None
        if toplevel:
            code = _codegen_template.format(expr=expr, obj=accessor)
        else:
            code = f"return {expr}"
        return CodeGen(code, typ=typ, recurse=recurse, **ndb.vars)

    ###########################
    # deserialize_is_standard #
    ###########################

    def deserialize_standard_pair(self, typ):
        t = get_origin(typ) or typ
        if issubclass(t, (int, float, str, bool, NoneType)):
            return (type[typ], typ)
        elif issubclass(t, list):
            return (type[typ], list)
        else:
            return (type[typ], dict)

    def deserialize_is_standard(self, typ, recursive=False):
        """Return whether deserialize_sync::(type[typ], typ) is standard.

        Codegen for standard implementations can be nested.
        """
        type_tuple = self.deserialize_standard_pair(typ)
        resolved = self.deserialize_sync.map.mro(type_tuple, specialize=False)
        rval = (
            resolved
            and resolved[0]
            and getattr(resolved[0][0].base_handler, "standard_codegen", False)
        )
        if rval and recursive:
            return rval and all(
                self.deserialize_is_standard(arg, recursive=True) for arg in get_args(typ)
            )
        else:
            return rval

    ###############
    # deserialize #
    ###############

    @standard_code_generator
    def deserialize(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        typ, vtyp = self.deserialize_standard_pair(t)
        if _compatible(vtyp, value) and self.deserialize_is_standard(t):
            if issubclass(value, TrackingProxy):
                return self.make_code(
                    t, "value", self.deserialize_sync.__ovld__.dispatch, toplevel=True, nest=False
                )
            else:
                return self.make_code(
                    t, "value", self.deserialize_sync.__ovld__.dispatch, toplevel=True
                )

    def deserialize(self, typ, value):
        try:
            return self.deserialize_sync(typ, value)
        except Exception as exc:
            self.deserialize_handle_exception(typ, value, exc)

    ####################
    # deserialize_sync #
    ####################

    @ovld
    @standard_code_generator
    def deserialize_sync(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        typ, vtyp = self.deserialize_standard_pair(t)
        if _compatible(vtyp, value):
            if issubclass(value, TrackingProxy):
                return self.make_code(t, "value", recurse, nest=False)
            else:
                return self.make_code(t, "value", recurse)

    @ovld(priority=10)
    def deserialize_sync(self, typ: type[object], value: TrackingProxy):
        try:
            return call_next(typ, value)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(exc=exc, ctx=get_annotations(value))

    @ovld(priority=-1)
    def deserialize_sync(self, typ: type[object], value: object):
        tv = type(value)
        if isinstance(value, TrackingProxy):
            tv = tv._self_cls
        raise TypeError(f"No way to deserialize {tv} as {typ}")

    ###############################
    # deserialize exception handler #
    ###############################

    @ovld(priority=10)
    def deserialize_handle_exception(self, typ, value, exc: ValidationError):
        raise

    def deserialize_handle_exception(self, typ, value: TrackingProxy, exc):
        raise ValidationError(exc=exc, ctx=value._self_ann)

    def deserialize_handle_exception(self, typ, value, exc):
        return self.deserialize(typ, TrackingProxy.make(value))


default = Deserializer()
deserialize = default.deserialize


default_check = Deserializer(validate_deserialization=True)
deserialize_check = default_check.deserialize
