from types import NoneType, UnionType
from typing import Union, get_args, get_origin

from ovld import CodeGen, OvldPerInstanceBase, call_next, code_generator, ovld, recurse

from .exc import ValidationError
from .proxy import TrackingProxy, get_annotations
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


def compatible(t1, t2):
    if issubclass(t2, TrackingProxy):
        t2 = t2._self_cls
    if (orig := get_origin(t1)) and orig not in (Union, UnionType):
        t1 = orig
    return issubclass(t2, t1)


class BaseTransformer(OvldPerInstanceBase):
    ###########
    # Codegen #
    ###########

    def default_codegen(self, ndb: NameDatabase, typ: type[object], accessor: str):
        t = ndb.stash(typ, prefix="T")
        return f"$recurse(self, {t}, {accessor})"

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

    #############
    # transform #
    #############

    @ovld(priority=-1)
    def transform(self, typ, value):
        try:
            return self.transform_sync(typ, value)
        except Exception as exc:
            self.handle_exception(typ, value, exc)

    @standard_code_generator
    def transform(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        typ, vtyp = self.standard_pair(t)
        if compatible(vtyp, value) and self.transform_is_standard(t):
            if issubclass(value, TrackingProxy):
                return self.make_code(
                    t, "value", self.transform_sync.__ovld__.dispatch, toplevel=True, nest=False
                )
            else:
                return self.make_code(
                    t, "value", self.transform_sync.__ovld__.dispatch, toplevel=True
                )

    ##################
    # transform_sync #
    ##################

    @ovld
    @standard_code_generator
    def transform_sync(self, typ: type[object], value: object):
        (t,) = get_args(typ)
        typ, vtyp = self.standard_pair(t)
        if compatible(vtyp, value):
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


class Transformer(BaseTransformer):
    validate_by_default = True

    def __init__(self, validate=None):
        self.validate = self.validate_by_default if validate is None else validate

    @classmethod
    def ovld_instance_key(cls, validate=False):
        return (("this", cls), ("validate", validate))
