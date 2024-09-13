from dataclasses import fields
from enum import Enum
from typing import Union

from ovld import Dataclass, OvldBase, call_next, ovld, recurse

from .exc import ValidationError, ValidationExceptionGroup
from .model import (
    Field,
    ListModel,
    MappingModel,
    Model,
    Multiple,
    Partial,
    StructuredModel,
    UnionModel,
)
from .proxy import Proxy, TrackingProxy, deprox, get_annotations, proxy

UnionAlias = type(Union[int, str])


def decompose(cls, default_args=[]):
    if hasattr(cls, "__origin__"):
        return cls.__origin__, cls.__args__
    else:
        return cls, default_args


class DataConverter(OvldBase):
    def __init__(self):
        self._model_cache = {}

    #########
    # model #
    #########

    @ovld(priority=100)
    def model(self, typ: type[object]):
        if typ not in self._model_cache:
            model = call_next(typ)
            self._model_cache[typ] = model
            if isinstance(model, Model):
                model.fill(self.model)
        return self._model_cache[typ]

    def model(self, typ: type[Union]):
        return UnionModel(original_type=typ, options=typ.__args__)

    def model(self, typ: type[object] | Model):
        return typ

    def model(self, typ: type[dict]):
        dt, [kt, vt] = decompose(typ, [str, object])
        return MappingModel(
            original_type=typ,
            builder=dt,
            extractor=dict,
            key_type=kt,
            element_type=vt,
        )

    def model(self, typ: type[list]):
        lt, [et] = decompose(typ, [object])
        return ListModel(
            original_type=typ,
            builder=lt,
            extractor=list,
            element_type=et,
        )

    def model(self, typ: type[Dataclass]):
        flds = fields(getattr(typ, "__origin__", typ))
        return StructuredModel(
            original_type=typ,
            builder=typ,
            fields={f.name: Field(type=f.type) for f in flds},
        )

    #############
    # serialize #
    #############

    def serialize(self, typ, value):
        pass

    #######################
    # deserialize_partial #
    #######################

    @ovld(priority=100)
    def deserialize_partial(self, to: object, frm: object):
        try:
            if not isinstance(frm, TrackingProxy):
                frm = TrackingProxy.make(frm)
            model = self.model(to)
            rval = call_next(model, frm)
            return proxy(rval, get_annotations(frm))
        except ValidationError as exc:
            return exc
        except Exception as exc:
            new_exc = ValidationError(exc, get_annotations(frm))
            new_exc.__traceback__ = exc.__traceback__
            return new_exc

    def deserialize_partial(self, to: StructuredModel, frm: dict):
        des = {k: recurse(to.fields[k].type, v) for k, v in frm.items()}
        return Partial(to.builder)(**des)

    def deserialize_partial(self, to: MappingModel, frm: dict):
        des = {
            recurse(to.key_type, k): recurse(to.element_type, v)
            for k, v in frm.items()
        }
        return Partial(to.builder)(des)

    def deserialize_partial(self, to: ListModel, frm: list):
        return Partial(to.builder)([recurse(to.element_type, x) for x in frm])

    def deserialize_partial(self, to: object, frm: Multiple):
        parts = [recurse(to, part) for part in frm.parts]
        if not all(isinstance(p, Partial) for p in parts):
            raise TypeError(
                "Cannot merge multiple sources because they have different types."
            )
        p1, *rest = parts
        for p in rest:
            if p.builder != p1.model:
                raise TypeError(
                    "Cannot merge multiple sources because they have different types."
                )
            p1.args += p.args
            p1.kwargs.update(p.kwargs)
        return p1

    def deserialize_partial(self, to: type[int], frm: int):
        return to(frm)

    def deserialize_partial(self, to: type[float], frm: float):
        return to(frm)

    def deserialize_partial(self, to: type[str], frm: str):
        return to(frm)

    def deserialize_partial(self, to: type[Enum], frm: str):
        return to(frm)

    #########
    # build #
    #########

    @ovld(priority=10)
    def build(self, obj: object):
        try:
            return call_next(deprox(obj) if isinstance(obj, Proxy) else obj)
        except Exception as exc:
            return (None, [ValidationError(exc, get_annotations(obj))])

    def build(self, part: Partial):
        args, aexcs = recurse(part.args)
        kwargs, kwexcs = recurse(part.kwargs)
        if aexcs or kwexcs:
            return (None, aexcs + kwexcs)
        else:
            return (part.builder(*args, **kwargs), [])

    def build(self, exc: ValidationError):
        return (None, [exc])

    def build(self, li: list | tuple):
        excs = []
        args = []
        for arg in li:
            value, more_excs = recurse(arg)
            excs.extend(more_excs)
            args.append(value)
        return (None if excs else args, excs)

    def build(self, d: dict):
        excs = []
        kwargs = {}
        for k, v in d.items():
            kwargs[k], more_excs = recurse(v)
            excs.extend(more_excs)
        return (None if excs else kwargs, excs)

    def build(self, x: object):
        return (x, [])

    ###############
    # deserialize #
    ###############

    @ovld
    def deserialize(self, to: object, frm: object):
        value, excs = self.build(self.deserialize_partial(to, frm))
        if excs:
            raise ValidationExceptionGroup(
                "Errors occurred during deserialization", excs
            )
        else:
            return value

    ##########
    # schema #
    ##########

    def schema(self):
        pass
