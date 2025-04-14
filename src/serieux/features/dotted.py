from ovld import Medley, call_next, ovld

from ..ctx import Context


def unflatten(d: dict):
    rval = {}
    split_keys = [(k.split("."), v) for k, v in d.items()]
    for parts, v in sorted(split_keys, key=lambda kv: len(kv[0])):
        current = rval
        for p in parts[:-1]:
            current = current.setdefault(p, {})
        current[parts[-1]] = v
    return rval


class DottedNotation(Medley):
    @ovld(priority=10)
    def deserialize(self, t: type[object], obj: dict, ctx: Context):
        if any("." in k for k in obj.keys()):
            return call_next(t, unflatten(obj), ctx)
        return call_next(t, obj, ctx)


# Not a default feature because it is disruptive
__default_features__ = None
