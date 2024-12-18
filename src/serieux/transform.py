from itertools import count
from types import NoneType, UnionType
from typing import Union, get_args, get_origin

from ovld import Code, OvldPerInstanceBase, call_next, code_generator, ovld, recurse

from .exc import ValidationError
from .proxy import TrackingProxy, get_annotations
from .utils import evaluate_hint

_toplevel_template = """
try:
    return $expr
except Exception as exc:
    return self.handle_exception($typ, $obj, exc)
"""

_intermediary_template = "return $expr"


class CodegenState:
    def __init__(self, nest=True):
        self.seen = set()
        self.nest = nest


def standard_code_generator(fn):
    fn.standard_codegen = True
    return code_generator(fn)


def compatible(t1, t2):
    if issubclass(t2, TrackingProxy):
        t2 = t2._self_cls
    if (orig := get_origin(t1)) and orig not in (Union, UnionType):
        t1 = orig
    return issubclass(t2, t1)


_gensym_count = count()


def gensym(*prefixes):
    if not prefixes:
        prefixes = ("tmp",)
    codes = [Code(f"{prefix}__{next(_gensym_count)}") for prefix in prefixes]
    return codes[0] if len(codes) == 1 else codes


class BaseTransformer(OvldPerInstanceBase):
    ###########
    # Codegen #
    ###########

    def default_codegen(self, state: CodegenState, typ: type[object], accessor: Code):
        return Code("$recurse(self, $typ, $accessor)", typ=typ, accessor=accessor)

    def guard_codegen(self, ndb, typ, accessor, body):
        if not self.validate:
            return body
        else:
            tmp = gensym()
            return Code(
                "$body if isinstance($tmp := $accessor, $otyp) else $dflt",
                body=body.sub(accessor=tmp),
                tmp=tmp,
                accessor=accessor,
                otyp=get_origin(typ) or typ,
                dflt=self.default_codegen(ndb, typ, tmp),
            )

    @ovld(priority=100)
    def codegen(self, state: CodegenState, typ: type[object], accessor, /):
        if (state.seen and not state.nest) or (
            typ in state.seen and typ not in (int, str, bool, NoneType)
        ):
            return self.default_codegen(state, typ, accessor)
        elif not state.seen or self.transform_is_standard(typ):
            # * state.seen is empty for the top level generation, and we always proceed.
            # * Otherwise, we are generating code recursively for subfields, but
            #   we only do this if the main serialize_sync method is the standard
            #   code generation method.
            state.seen.add(typ)
            return call_next(state, typ, accessor)
        else:
            return self.default_codegen(state, typ, accessor)

    def make_code(self, typ: type[object], accessor, recurse, toplevel=False, nest=True):
        accessor = accessor if isinstance(accessor, Code) else Code(accessor)
        typ = evaluate_hint(typ)
        state = CodegenState(nest=nest)
        try:
            expr = self.codegen(state, typ, accessor)
        except NotImplementedError:
            return None
        template = _toplevel_template if toplevel else _intermediary_template
        return Code(template, typ=typ, recurse=recurse, obj=accessor, expr=expr)

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
