from dataclasses import dataclass, fields
from itertools import pairwise
from types import NoneType, UnionType
from typing import Union, get_args, get_origin

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
from .utils import JSONType, NameDatabase, UnionAlias, evaluate_hint

_codegen_template = """
try:
    return {expr}
except Exception as exc:
    return self.handle_exception($typ, {obj}, exc)
"""


def _compatible(t1, t2):
    if issubclass(t2, TrackingProxy):
        t2 = t2._self_cls
    return issubclass(t2, t1)


class Tell:
    def cost(self):
        return 1


@dataclass(frozen=True)
class TypeTell(Tell):
    t: type

    def gen(self, ndb, accessor):
        t = ndb.stash(self.t, prefix="T")
        return f"isinstance({accessor}, {t})"


@dataclass(frozen=True)
class KeyTell(Tell):
    key: str

    def gen(self, ndb, accessor):
        k = ndb.stash(self.key, prefix="K")
        return f"(isinstance({accessor}, dict) and {k} in {accessor})"

    def cost(self):
        return 2


class Deserializer(OvldPerInstanceBase):
    def __init__(self, validate=True):
        self.validate = validate

    @classmethod
    def ovld_instance_key(cls, validate=True):
        return (("this", cls), ("validate", validate))

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
        if (ndb.seen and not ndb.nest) or (
            typ in ndb.seen and typ not in (int, str, bool, NoneType)
        ):
            return self.default_codegen(ndb, typ, accessor)
        elif not ndb.seen or self.transform_is_standard(typ):
            # * ndb.seen is empty for the top level generation, and we always proceed.
            # * Otherwise, we are generating code recursively for subfields, but
            #   we only do this if the main serialize_sync method is the standard
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
        cons = ndb.stash(dc, prefix="T")
        for f in fields(dc):
            ftype = evaluate_hint(f.type, ctx=dc, typesub=tsub)
            setter = recurse(ndb, ftype, f"{accessor}['{f.name}']")
            parts.append(setter)
        return f"{cons}(" + ",".join(parts) + ")"

    def codegen(self, ndb: NameDatabase, x: type[dict], accessor, /):
        kt, vt = get_args(x)
        kt = evaluate_hint(kt)
        vt = evaluate_hint(vt)
        ktmp = ndb.gensym("key")
        vtmp = ndb.gensym("value")
        kx = recurse(ndb, kt, ktmp)
        vx = recurse(ndb, vt, vtmp)
        return f"{{{kx}: {vx} for {ktmp}, {vtmp} in {accessor}.items()}}"

    def codegen(self, ndb: NameDatabase, x: type[list], accessor, /):
        (et,) = get_args(x)
        et = evaluate_hint(et)
        etmp = ndb.gensym("elt")
        ex = recurse(ndb, et, etmp)
        # TODO: check that it is a list, because this will accidentally work with dicts
        return f"[{ex} for {etmp} in {accessor}]"

    def codegen(self, ndb: NameDatabase, x: type[UnionAlias], accessor, /):
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

        code = recurse(ndb, o1, accessor)
        for tls, opt in rest:
            ocode = recurse(ndb, opt, accessor)
            tl = min(tls, key=lambda tl: tl.cost())
            cond = tl.gen(ndb, accessor)
            code = f"({ocode} if {cond} else {code})"
        return code

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

    def make_code(self, typ: type[object], accessor, recurse, toplevel=False, nest=True):
        typ = evaluate_hint(typ)
        ndb = NameDatabase(nest=nest)
        try:
            expr = self.codegen(ndb, typ, accessor)
        except NotImplementedError:
            return None
        if toplevel:
            code = _codegen_template.format(expr=expr, obj=accessor)
        else:
            code = f"return {expr}"
        return CodeGen(code, typ=typ, recurse=recurse, **ndb.vars)

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

    def transform_is_standard(self, typ, recursive=False):
        """Return whether transform_sync::(type[typ], typ) is standard.

        Codegen for standard implementations can be nested.
        """
        type_tuple = self.standard_pair(typ)
        resolved = self.transform_sync.map.mro(type_tuple, specialize=False)
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

    ###############
    # deserialize #
    ###############

    @standard_code_generator
    def transform(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        typ, vtyp = self.standard_pair(t)
        if _compatible(vtyp, value) and self.transform_is_standard(t):
            if issubclass(value, TrackingProxy):
                return self.make_code(
                    t, "value", self.transform_sync.__ovld__.dispatch, toplevel=True, nest=False
                )
            else:
                return self.make_code(
                    t, "value", self.transform_sync.__ovld__.dispatch, toplevel=True
                )

    def transform(self, typ, value):
        try:
            return self.transform_sync(typ, value)
        except Exception as exc:
            self.handle_exception(typ, value, exc)

    ####################
    # transform_sync #
    ####################

    @ovld
    @standard_code_generator
    def transform_sync(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        typ, vtyp = self.standard_pair(t)
        if _compatible(vtyp, value):
            if issubclass(value, TrackingProxy):
                return self.make_code(t, "value", recurse, nest=False)
            else:
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


default = Deserializer()
deserialize = default.transform


default_check = Deserializer(validate=True)
deserialize_check = default_check.transform
