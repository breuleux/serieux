from dataclasses import fields
from types import NoneType
from typing import get_args, get_origin

from ovld import Dataclass, call_next, extend_super, ovld, recurse

from .transform import Transformer, standard_code_generator
from .utils import JSONType, NameDatabase, UnionAlias, evaluate_hint


class Serializer(Transformer):
    validate_by_default = False

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

    #################
    # standard_pair #
    #################

    def standard_pair(self, typ):
        return (type[typ], typ)

    #############
    # transform #
    #############

    @extend_super
    @standard_code_generator
    def transform(self, x: object):
        if self.transform_is_standard(x):
            return self.make_code(x, "x", self.transform_sync.__ovld__.dispatch, toplevel=True)

    @ovld(priority=-1)
    def transform(self, x):
        typ = type(x)
        try:
            return self.transform_sync(typ, x)
        except Exception as exc:
            self.handle_exception(typ, x, exc)


default = Serializer()
serialize = default.transform

default_check = Serializer(validate=True)
serialize_check = default_check.transform
