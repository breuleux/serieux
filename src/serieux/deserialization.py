from dataclasses import dataclass, fields
from itertools import pairwise
from types import NoneType, UnionType
from typing import Union, get_args, get_origin

from ovld import Dataclass, call_next, extend_super, ovld, recurse

from .transform import Transformer
from .utils import JSONType, NameDatabase, UnionAlias, evaluate_hint


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


class Deserializer(Transformer):
    validate_by_default = True

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

    @extend_super
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
        return self.guard_codegen(ndb, list, accessor, f"[{ex} for {etmp} in {accessor}]")

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


default = Deserializer()
deserialize = default.transform


default_check = Deserializer(validate=True)
deserialize_check = default_check.transform
