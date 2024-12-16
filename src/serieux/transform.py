from types import NoneType
from typing import get_args

from ovld import CodeGen, OvldPerInstanceBase, call_next, code_generator, ovld

from .exc import ValidationError
from .proxy import TrackingProxy
from .utils import NameDatabase, evaluate_hint

_codegen_template = """
try:
    return {expr}
except Exception as exc:
    return self.handle_exception($typ, {obj}, exc)
"""


def standard_code_generator(fn):
    fn.standard_codegen = True
    return code_generator(fn)


class BaseTransformer(OvldPerInstanceBase):
    ###########
    # Codegen #
    ###########

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


class Transformer(BaseTransformer):
    validate_by_default = True

    def __init__(self, validate=None):
        self.validate = self.validate_by_default if validate is None else validate

    @classmethod
    def ovld_instance_key(cls, validate=False):
        return (("this", cls), ("validate", validate))
