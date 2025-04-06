from dataclasses import field, fields, make_dataclass
from functools import reduce

from ovld import Medley, call_next, ovld, recurse

from .ctx import Context
from .exc import ValidationError
from .model import Modelizable, model
from .typetags import NewTag

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
    m = model(t)
    fields = [(f.name, partialize(f.type), field(default=NOT_GIVEN)) for f in m.fields]
    fields.append(
        ("_serieux_ctx", Context, field(default=NOT_GIVEN, metadata={"serieux_metavar": "$ctx"}))
    )
    dc = make_dataclass(
        cls_name=f"Partial[{t.__name__}]",
        bases=(PartialBase,),
        fields=fields,
    )
    dc._constructor = m.constructor
    return dc


@ovld
def partialize(t: object):
    return t


###################
# Implementations #
###################


class PartialFeature(Medley):
    def deserialize(self, t: type[object], obj: Sources, ctx: Context, /):
        parts = [recurse(Partial[t], src, ctx) for src in obj.sources]
        return instantiate(reduce(merge, parts))


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
def instantiate(xs: dict):
    return {k: recurse(v) for k, v in xs.items()}


@ovld
def instantiate(xs: list):
    return [recurse(v) for v in xs]


@ovld
def instantiate(p: PartialBase):
    dc = p._constructor
    args = {
        f.name: recurse(value)
        for f in fields(dc)
        if (value := getattr(p, f.name)) is not NOT_GIVEN
    }
    try:
        return dc(**args)
    except Exception as exc:
        raise ValidationError(exc=exc, ctx=p._serieux_ctx)


@ovld
def instantiate(x: object):
    return x
