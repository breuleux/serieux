from dataclasses import fields
from typing import get_args, get_origin

from ovld import (
    CodeGen,
    Dataclass,
    OvldPerInstanceBase,
    code_generator,
    ovld,
    recurse,
)

from .utils import NameDatabase, evaluate_hint


class Deserializer(OvldPerInstanceBase):
    def __init__(self, validate_deserialization=True):
        self.validate_deserialization = validate_deserialization

    @classmethod
    def ovld_instance_key(cls, validate_deserialization=True):
        return (("validate_deserialization", validate_deserialization),)

    #######################
    # deserialize_codegen #
    #######################

    def _guard(self, ndb, typ, accessor, body):
        if not self.validate_deserialization:
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
            code = f"({body} if isinstance({tmp} := {accessor}, {otyp_embed}) else $recurse(None, {typ_embed}, {tmp}))"
            return code

    def deserialize_codegen(
        self, ndb: NameDatabase, dc: type[Dataclass], accessor, /
    ):
        parts = []
        cons = ndb.stash(dc, prefix="T")
        for f in fields(dc):
            ftype = evaluate_hint(f.type, ctx=dc)
            setter = recurse(ndb, ftype, f"{accessor}['{f.name}']")
            parts.append(setter)
        return f"{cons}(" + ",".join(parts) + ")"

    def deserialize_codegen(
        self, ndb: NameDatabase, x: type[dict], accessor, /
    ):
        kt, vt = get_args(x)
        kt = evaluate_hint(kt)
        vt = evaluate_hint(vt)
        ktmp = ndb.gensym("key")
        vtmp = ndb.gensym("value")
        kx = recurse(ndb, kt, ktmp)
        vx = recurse(ndb, vt, vtmp)
        return f"{{{kx}: {vx} for {ktmp}, {vtmp} in {accessor}.items()}}"

    def deserialize_codegen(
        self, ndb: NameDatabase, x: type[list], accessor, /
    ):
        (et,) = get_args(x)
        et = evaluate_hint(et)
        etmp = ndb.gensym("elt")
        ex = recurse(ndb, et, etmp)
        # TODO: check that it is a list, because this will accidentally work with dicts
        return f"[{ex} for {etmp} in {accessor}]"

    def deserialize_codegen(
        self,
        ndb: NameDatabase,
        x: type[int] | type[str] | type[bool],
        accessor,
        /,
    ):
        return self._guard(ndb, x, accessor, "$$$")

    def make_code(self, typ, accessor, recurse):
        ndb = NameDatabase()
        expr = self.deserialize_codegen(ndb, typ, accessor)
        return CodeGen(f"return {expr}", recurse=recurse, **ndb.vars)

    #############
    # serialize #
    #############

    @ovld
    @code_generator
    def deserialize(self, typ: type[Dataclass], frm: object):
        (x,) = get_args(typ)
        return self.make_code(x, "frm", recurse)


default = Deserializer()
