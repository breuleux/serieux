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
    recurse,
)


class NameDatabase:
    def __init__(self):
        self.count = count()
        self.vars = {}

    def gensym(self, prefix):
        return f"{prefix}{next(self.count)}"

    def stash(self, v, prefix="TMP"):
        var = f"{prefix}{next(self.count)}"
        self.vars[var] = v
        return f"${var}"


class Serializer(OvldPerInstanceBase):
    def __init__(self, validate_serialization=False):
        self.validate_serialization = validate_serialization

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

    def serialize_codegen(
        self, ndb: NameDatabase, dc: type[Dataclass], accessor, /
    ):
        parts = []
        for f in fields(dc):
            setter = recurse(ndb, f.type, f"$$$.{f.name}")
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

    def serialize_codegen(self, typ: type[object], accessor, /):
        ndb = NameDatabase()
        expr = self.serialize_codegen(ndb, typ, accessor)
        return CodeGen(f"return {expr}", recurse=recurse, **ndb.vars)

    #############
    # serialize #
    #############

    @code_generator
    def serialize(self, x: object):
        return self.serialize_codegen(x, "x")

    @code_generator
    def serialize(self, typ: type[Dataclass], value: object):
        return self.serialize_codegen(typ, "value")


default = Serializer()
