from dataclasses import field, fields, make_dataclass
from functools import reduce

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError, ValidationExceptionGroup
from ..model import Model, Modelizable, model
from ..typetags import NewTag

#############
# Constants #
#############


Partial = NewTag["Partial"]


class NOT_GIVEN_T:
    pass


NOT_GIVEN = NOT_GIVEN_T()


class PartialBase:
    pass


class Sources:
    def __init__(self, *sources):
        self.sources = sources


@ovld
def partialize(t: type[Modelizable]):
    if issubclass(t, Model):
        return recurse(t.original_type)
    if issubclass(t, PartialBase):
        return t
    m = model(t)
    fields = [
        (
            f.name,
            partialize(f.type),
            field(default=NOT_GIVEN, metadata={"description": f.description}),
        )
        for f in m.fields
    ]
    fields.append(
        ("_serieux_ctx", Context, field(default=NOT_GIVEN, metadata={"serieux_metavar": "$ctx"}))
    )
    dc = make_dataclass(
        cls_name=f"Partial[{t.__name__}]",
        bases=(PartialBase,),
        fields=fields,
        namespace={"_constructor": m.constructor},
    )
    return dc


@ovld(priority=1)
def partialize(t: type[Partial]):
    return recurse(t.pushdown())


@ovld
def partialize(t: object):
    return Partial[t]


###################
# Implementations #
###################


class PartialBuilding(Medley):
    @ovld(priority=1)
    def deserialize(self, t: type[Partial[object]], obj: object, ctx: Context, /):
        try:
            return call_next(t, obj, ctx)
        except ValidationError as exc:
            return exc

    def deserialize(self, t: type[object], obj: Sources, ctx: Context, /):
        parts = [recurse(Partial[t], src, ctx) for src in obj.sources]
        rval = instantiate(reduce(merge, parts))
        if isinstance(rval, (ValidationError, ValidationExceptionGroup)):
            raise rval
        return rval

    def deserialize(self, t: type[PartialBase], obj: object, ctx: Context, /):
        # Fallback for alternative ways to deserialize the original object
        return recurse(t._constructor, obj, ctx)


@model.register
def _(p: type[Partial[object]]):
    return call_next(partialize(p.pushdown()))


######################
# Merge partial data #
######################


@ovld
def merge(x: object, y: NOT_GIVEN_T):
    return x


@ovld
def merge(x: NOT_GIVEN_T, y: object):
    return y


@ovld
def merge(x: NOT_GIVEN_T, y: NOT_GIVEN_T):
    return NOT_GIVEN


@ovld
def merge(x: PartialBase, y: PartialBase):
    assert x._constructor is y._constructor
    args = {}
    for f in fields(type(x)):
        xv = getattr(x, f.name)
        yv = getattr(y, f.name)
        args[f.name] = recurse(xv, yv)
    return type(x)(**args)


@ovld
def merge(x: PartialBase, y: object):
    if x._constructor is not type(y):
        raise ValidationError("Incompatible constructors.")
    return recurse(x, type(x)(**vars(y)))


@ovld
def merge(x: object, y: PartialBase):
    if y._constructor is not type(x):
        raise ValidationError("Incompatible constructors.")
    return recurse(type(y)(**vars(x)), y)


@ovld
def merge(x: dict, y: dict):
    result = dict(x)
    for k, v in y.items():
        result[k] = recurse(result.get(k, NOT_GIVEN), v)
    return result


@ovld
def merge(x: list, y: list):
    return x + y


@ovld
def merge(x: object, y: object):
    return y


############################
# Instantiate partial data #
############################


@ovld
def instantiate(xs: list):
    rval = []
    errs = []
    for v in xs:
        value = recurse(v)
        if isinstance(value, ValidationError):
            errs.append(value)
        elif isinstance(value, ValidationExceptionGroup):
            errs.extend(value.exceptions)
        else:
            rval.append(value)
    if errs:
        return ValidationExceptionGroup("Some errors occurred", errs)
    return rval


@ovld
def instantiate(xs: dict):
    rval = {}
    errs = []
    for k, v in xs.items():
        if v is NOT_GIVEN:
            continue
        value = recurse(v)
        if isinstance(value, ValidationError):
            errs.append(value)
        elif isinstance(value, ValidationExceptionGroup):
            errs.extend(value.exceptions)
        else:
            rval[k] = value
    if errs:
        return ValidationExceptionGroup("Some errors occurred", errs)
    return rval


@ovld
def instantiate(p: PartialBase):
    dc = p._constructor
    args = recurse({f.name: getattr(p, f.name) for f in fields(dc)})
    if isinstance(args, (ValidationError, ValidationExceptionGroup)):
        return args
    try:
        return dc(**args)
    except Exception as exc:
        return ValidationError(exc=exc, ctx=p._serieux_ctx)


@ovld
def instantiate(x: object):
    return x


# Add as a default feature in serieux.Serieux
__default_features__ = PartialBuilding
