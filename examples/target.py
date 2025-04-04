import importlib
from json import JSONEncoder

from ovld import Medley, ovld, recurse
from ovld.dependent import HasKey

from serieux import Context, Serieux

##################
# Implementation #
##################


class Target(Medley):
    @ovld
    def deserialize(self, t: type[object], obj: HasKey["_target_"], ctx: Context):  # noqa
        obj = dict(obj)
        symbol = obj.pop("_target_")
        module, symbol = symbol.split(".", 1)
        target = getattr(importlib.import_module(module), symbol)
        kwargs = {k: recurse(type(v), v, ctx) for k, v in obj.items()}
        return target(**kwargs)


sx = Serieux() + Target()


#################
# Demonstration #
#################


def main():
    data = {
        "_target_": "json.JSONEncoder",
        "indent": 3,
    }
    result = sx.deserialize(object, data)
    assert isinstance(result, JSONEncoder)
    print(result.encode({"x": 3, "y": 4}))


if __name__ == "__main__":
    main()
