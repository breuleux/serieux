from dataclasses import dataclass, field, fields, make_dataclass, replace
from functools import reduce
from typing import TYPE_CHECKING, Annotated, Any, TypeAlias

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import (
    NotGivenError,
    SerieuxError,
    ValidationError,
    ValidationExceptionGroup,
    merge_errors,
)
from ..instructions import Instruction, T, has_instruction, strip
from ..model import FieldModelizable, ListModelizable, Model, model
from ..priority import HI4
from .proxy import LazyProxy

#############
# Constants #
#############


if TYPE_CHECKING:
    Partial: TypeAlias = Annotated[T, None]
else:
    Partial = Instruction("Partial", annotation_priority=1, inherit=True)


class NOT_GIVEN_T:
    pass


NOT_GIVEN = NOT_GIVEN_T()


class PartialBase:
    pass


class AllTrails(Context):
    pass


class Sources:
    def __init__(self, *sources):
        self.sources = []
        for src in sources:
            if isinstance(src, Sources):  # pragma: no cover
                self.sources.extend(src.sources)
            else:
                self.sources.append(src)


@ovld
def partialize(t: type[FieldModelizable]):
    m = model(t)
    fields = [
        (
            f.name,
            Partial[f.type],
            field(default=NOT_GIVEN, metadata={"description": f.description, **f.metadata}),
        )
        for f in m.fields
    ]
    fields.append(
        (
            "_serieux_ctx",
            Context,
            field(repr=False, default=NOT_GIVEN, metadata={"serieux_metavar": "$ctx"}),
        )
    )
    dc = make_dataclass(
        cls_name=f"Partial[{t.__name__}]",
        bases=(PartialBase,),
        fields=fields,
        namespace={"_constructor": staticmethod(m.constructor), "_model": m},
    )
    return dc


@dataclass
class PartialListModelizable:
    elements: list


@ovld(priority=1)
def partialize(t: type[ListModelizable]):
    m = model(t)
    ef = m.element_field

    class PLM(PartialListModelizable):
        _model = m

        @classmethod
        def serieux_model(cls, call_next):
            return Model(
                original_type=cls,
                element_field=replace(ef, type=Partial[ef.type]),
                list_constructor=lambda xs: PLM(list(xs)),
            )

    return PLM


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
    @ovld(priority=HI4.next())
    def deserialize(self, t: type[Any @ Partial], obj: object, ctx: Context, /):
        try:
            return call_next(t, obj, ctx)
        except SerieuxError as exc:
            return exc
        except Exception as exc:
            return ValidationError(exc=exc)

    @ovld(priority=HI4.next())
    def deserialize(self, t: Any, obj: Sources, ctx: Context, /):
        is_partial = has_instruction(t, Partial)
        parts = []
        for src in obj.sources:
            try:
                parts.append(recurse(t if is_partial else Partial[t], src, ctx))
            except SerieuxError as exc:  # pragma: no cover
                parts.append(exc)
        merged = reduce(merge, parts)
        if is_partial:
            return merged
        rval = instantiate(merged)
        if isinstance(rval, SerieuxError):
            raise rval
        return rval

    @ovld(priority=HI4.next())
    def deserialize(self, t: Any, obj: object, ctx: AllTrails, /):
        data = obj if isinstance(obj, Sources) else Sources(obj)
        return recurse(t, data, ctx - AllTrails)


@model.register(priority=2)
def _(p: type[Any @ Partial]):
    return call_next(partialize(strip(p, Partial)))


######################
# Merge partial data #
######################


@ovld(priority=2)
def merge(x: object, y: NotGivenError):
    return x


@ovld(priority=2)
def merge(x: NotGivenError, y: object):  # pragma: no cover
    return y


@ovld(priority=2)
def merge(x: object, y: SerieuxError):
    return y


@ovld(priority=2)
def merge(x: SerieuxError, y: object):
    return x


@ovld(priority=3)
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
    xm = x._model
    ym = y._model
    if xm is ym or xm.is_submodel_of(ym):
        main = type(x)
    elif ym.is_submodel_of(xm):
        main = type(y)
    else:
        raise ValidationError(
            f"Cannot merge sources because of incompatible constructors: '{xm}', '{ym}'"
        )
    args = {}
    for f in fields(main):
        xv = getattr(x, f.name, NOT_GIVEN)
        yv = getattr(y, f.name, NOT_GIVEN)
        args[f.name] = recurse(xv, yv)
    return main(**args)


@ovld
def merge(x: PartialBase, y: object):
    if (xc := x._model) is not model(type(y)):
        raise ValidationError(
            f"Cannot merge sources because of incompatible constructors: '{xc}', '{type(y)}'."
        )
    props = x._model.property_names
    kwargs = {k: v for k, v in vars(y).items() if k in props}
    return recurse(x, type(x)(**kwargs))


@ovld
def merge(x: object, y: PartialBase):
    if (yc := y._model) is not model(type(x)):
        raise ValidationError(
            f"Cannot merge sources because of incompatible constructors: '{type(x)}', '{yc}'."
        )
    props = y._model.property_names
    kwargs = {k: v for k, v in vars(x).items() if k in props}
    return recurse(type(y)(**kwargs), y)


@ovld
def merge(x: dict, y: dict):
    result = type(x)(x)
    for k, v in y.items():
        result[k] = recurse(result.get(k, NOT_GIVEN), v)
    return result


@ovld
def merge(x: PartialListModelizable, y: PartialListModelizable):
    assert x._model is y._model
    return type(x)(x.elements + y.elements)


@ovld
def merge(x: list, y: list):
    return x + y


@ovld
def merge(x: LazyProxy, y: LazyProxy):
    return LazyProxy(lambda: recurse(x._obj, y._obj), x._type)


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
    rval = type(xs)()
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
    args = recurse({f.name: getattr(p, f.name) for f in p._model.fields})
    if isinstance(args, SerieuxError):
        return args
    try:
        return dc(**args)
    except Exception as exc:
        return ValidationError(exc=exc, ctx=p._serieux_ctx)


@ovld
def instantiate(p: PartialListModelizable):
    elems = recurse(p.elements)
    if isinstance(elems, SerieuxError):
        return elems
    return p._model.list_constructor(elems)


@ovld
def instantiate(x: LazyProxy):
    def do():
        rval = recurse(x._obj)
        if isinstance(rval, SerieuxError):
            raise rval
        return rval

    return LazyProxy(do, x._type)


@ovld
def instantiate(x: object):
    return x
