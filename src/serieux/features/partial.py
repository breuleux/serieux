from dataclasses import field, fields, make_dataclass
from functools import reduce

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import SerieuxError, ValidationError, ValidationExceptionGroup, merge_errors
from ..instructions import NewInstruction
from ..model import Modelizable, model
from ..utils import PRIO_HIGH, PRIO_LOW

#############
# Constants #
#############


Partial = NewInstruction["Partial"]


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


@ovld
def partialize(t: type[PartialBase]):  # pragma: no cover
    return t


@ovld
def partialize(t: object):
    return Partial[t]


###################
# Implementations #
###################


class PartialBuilding(Medley):
    @ovld(priority=PRIO_HIGH)
    def deserialize(self, t: type[Partial[object]], obj: object, ctx: Context, /):
        try:
            return call_next(t, obj, ctx)
        except SerieuxError as exc:
            return exc

    @ovld(priority=PRIO_HIGH)
    def deserialize(self, t: type[object], obj: Sources, ctx: Context, /):
        parts = [recurse(Partial[t], src, ctx) for src in obj.sources]
        rval = instantiate(reduce(merge, parts))
        if isinstance(rval, SerieuxError):
            raise rval
        return rval

    @ovld(priority=PRIO_LOW)
    def deserialize(self, t: type[PartialBase], obj: object, ctx: Context, /):
        # Fallback for alternative ways to deserialize the original object
        return recurse(t._constructor, obj, ctx)


@model.register
def _(p: type[Partial[object]]):
    return call_next(partialize(p.pushdown()))


######################
# Merge partial data #
######################


@ovld(priority=2)
def merge(x: object, y: SerieuxError):
    return y


@ovld(priority=2)
def merge(x: SerieuxError, y: object):
    return x


@ovld(priority=2)
def merge(x: SerieuxError, y: SerieuxError):
    return ValidationExceptionGroup("Some errors occurred", [x, y])


@ovld(priority=1)
def merge(x: object, y: NOT_GIVEN_T):
    return x


@ovld(priority=1)
def merge(x: NOT_GIVEN_T, y: object):
    return y


@ovld(priority=1)
def merge(x: NOT_GIVEN_T, y: NOT_GIVEN_T):
    return NOT_GIVEN


@ovld
def merge(x: PartialBase, y: PartialBase):
    if (xc := x._constructor) is not (yc := y._constructor):
        raise ValidationError(
            f"Cannot merge sources because of incompatible constructors: '{xc}', '{yc}'"
        )
    args = {}
    for f in fields(type(x)):
        xv = getattr(x, f.name)
        yv = getattr(y, f.name)
        args[f.name] = recurse(xv, yv)
    return type(x)(**args)


@ovld
def merge(x: PartialBase, y: object):
    if (xc := x._constructor) is not type(y):
        raise ValidationError(
            f"Cannot merge sources because of incompatible constructors: '{xc}', '{type(y)}'."
        )
    return recurse(x, type(x)(**vars(y)))


@ovld
def merge(x: object, y: PartialBase):
    if (yc := y._constructor) is not type(x):
        raise ValidationError(
            f"Cannot merge sources because of incompatible constructors: '{type(x)}', '{yc}'."
        )
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
    err = None
    for v in xs:
        value = recurse(v)
        if isinstance(value, SerieuxError):
            err = merge_errors(err, value)
        else:
            rval.append(value)
    return err if err else rval


@ovld
def instantiate(xs: dict):
    rval = {}
    err = None
    for k, v in xs.items():
        if v is NOT_GIVEN:
            continue
        value = recurse(v)
        if isinstance(value, SerieuxError):
            err = merge_errors(err, value)
        else:
            rval[k] = value
    return err if err else rval


@ovld
def instantiate(p: PartialBase):
    dc = p._constructor
    args = recurse({f.name: getattr(p, f.name) for f in fields(dc)})
    if isinstance(args, SerieuxError):
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
