from ovld import Medley, call_next, recurse


class Schema(dict):
    def compile(self, **kwargs):
        return SchemaCompiler(**kwargs)(self)

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)


class SchemaCompiler(Medley):
    use_defs: bool = False
    root: bool = True

    def __post_init__(self):
        self.refs = {}
        self.defs = {}
        self.done = set()

    def __call__(self, x: object):
        rval = recurse(x, ("#",))
        if self.root:
            rval["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        return rval

    def __call__(self, d: dict, pth: tuple):
        return {k: recurse(v, (*pth, k)) for k, v in d.items()}

    def __call__(self, xs: list, pth: tuple):
        return [recurse(x, (*pth, str(i))) for i, x in enumerate(xs)]

    def __call__(self, x: object, pth: tuple):
        return x

    def __call__(self, x: Schema, pth: tuple):
        if x in self.refs:
            if x in self.done and x.get("type", "object") != "object":
                return call_next(x, pth)
            else:
                return {"$ref": "/".join(self.refs[x])}
        else:
            self.refs[x] = pth
            rval = call_next(x, pth)
            self.done.add(x)
            return rval
