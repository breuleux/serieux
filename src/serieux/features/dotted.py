from typing import Any

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..model import FieldModelizable
from ..priority import HI2


def unflatten(d: dict, allow_lists=False):
    rval = {}
    split_keys = [(k.split("."), v) for k, v in d.items()]
    for parts, v in sorted(split_keys, key=lambda kv: len(kv[0])):
        current = rval
        for p in parts[:-1]:
            current = current.setdefault(p, {})
        current[parts[-1]] = v
    return rval if not allow_lists else _convert_lists(rval)


@ovld
def _convert_lists(obj: dict):
    obj = {k: recurse(v) for k, v in obj.items()}
    if all(k.isdigit() for k in obj.keys()):
        indices = sorted(int(k) for k in obj.keys())
        if indices != list(range(len(indices))):
            raise ValueError(f"List indices have gaps: {indices}")
        return [obj[str(i)] for i in range(len(indices))]
    return obj


@ovld
def _convert_lists(obj: object):
    return obj


class DottedNotation(Medley):
    @ovld(priority=HI2)
    def deserialize(self, t: Any, obj: dict, ctx: Context):
        if issubclass(t, FieldModelizable) and any("." in k for k in obj.keys()):
            return call_next(t, unflatten(obj), ctx)
        return call_next(t, obj, ctx)
