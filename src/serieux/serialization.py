from dataclasses import fields
from itertools import count
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

from .core import UnionAlias
from .model import evaluate_hint


class NameDatabase:
    def __init__(self):
        self.count = count()
        self.vars = {}
        self.seen = set()

    def gensym(self, prefix):
        return f"{prefix}{next(self.count)}"

    def stash(self, v, prefix="TMP"):
        var = f"{prefix}{next(self.count)}"
        self.vars[var] = v
        return f"${var}"


class Serializer(OvldPerInstanceBase):
    def __init__(self, validate_serialization=False):
        self.validate_serialization = validate_serialization

    @classmethod
    def ovld_instance_key(cls, validate_serialization=False):
        return (("validate_serialization", validate_serialization),)

    #####################
    # serialize_codegen #
    #####################

    def _guard(self, ndb, typ, accessor, body):
        if not self.validate_serialization:
            return body.replace("$$$", accessor)
        else:
            tmp = ndb.gensym("tmp")
            otyp = get_origin(typ) or typ
            typ_embed = ndb.stash(typ, prefix="T")
            if typ is otyp:
                otyp_embed = typ_embed
            else:
                otyp_embed = ndb.stash(otyp, prefix="T")
            body = body.replace("$$$", tmp)
            code = f"({body} if isinstance({tmp} := {accessor}, {otyp_embed}) else $recurse({typ_embed}, {accessor}))"
            return code

    @ovld(priority=100)
    def serialize_codegen(
        self, ndb: NameDatabase, typ: type[object], accessor, /
    ):
        if typ in ndb.seen and typ not in (int, str, bool, NoneType):
            t = ndb.stash(typ, prefix="T")
            return f"$recurse({t}, {accessor})"
        else:
            ndb.seen.add(typ)
            return call_next(ndb, typ, accessor)

    def serialize_codegen(
        self, ndb: NameDatabase, dc: type[Dataclass], accessor, /
    ):
        parts = []
        for f in fields(dc):
            ftype = evaluate_hint(f.type, ctx=dc)
            setter = recurse(ndb, ftype, f"$$$.{f.name}")
            parts.append(f"'{f.name}': {setter}")
        code = "{" + ",".join(parts) + "}"
        return self._guard(ndb, dc, accessor, code)

    def serialize_codegen(self, ndb: NameDatabase, x: type[dict], accessor, /):
        kt, vt = get_args(x)
        ktmp = ndb.gensym("key")
        vtmp = ndb.gensym("value")
        kx = recurse(ndb, kt, ktmp)
        vx = recurse(ndb, vt, vtmp)
        code = f"{{{kx}: {vx} for {ktmp}, {vtmp} in $$$.items()}}"
        return self._guard(ndb, x, accessor, code)

    def serialize_codegen(self, ndb: NameDatabase, x: type[list], accessor, /):
        (et,) = get_args(x)
        etmp = ndb.gensym("elt")
        ex = recurse(ndb, et, etmp)
        return self._guard(ndb, x, accessor, f"[{ex} for {etmp} in $$$]")

    def serialize_codegen(
        self,
        ndb: NameDatabase,
        x: type[int] | type[str] | type[bool],
        accessor,
        /,
    ):
        return self._guard(ndb, x, accessor, "$$$")

    def serialize_codegen(
        self, ndb: NameDatabase, x: type[NoneType], accessor, /
    ):
        if self.validate_serialization:
            tmp = ndb.gensym("tmp")
            return f"({tmp} if ({tmp} := {accessor}) is None else {call_next(ndb, x, tmp)})"
        else:
            return accessor

    def serialize_codegen(
        self, ndb: NameDatabase, x: type[object], accessor, /
    ):
        t = ndb.stash(x, prefix="T")
        return f"$recurse({t}, {accessor})"

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

    def make_code(self, typ: type[object], accessor, recurse, /):
        ndb = NameDatabase()
        expr = self.serialize_codegen(ndb, typ, accessor)
        return CodeGen(f"return {expr}", recurse=recurse, **ndb.vars)

    #############
    # serialize #
    #############

    @code_generator
    def serialize(self, x: object):
        return self.make_code(x, "x", recurse)

    @code_generator
    def serialize(self, typ: type[Dataclass], value: object):
        (x,) = get_args(typ)
        return self.make_code(x, "value", recurse)


default = Serializer()
