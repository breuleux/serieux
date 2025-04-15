from enum import Enum
from typing import Counter

from ovld import Medley, call_next, recurse


class Schema(dict):
    def __init__(self, t):
        self.for_type = t
        super().__init__()

    def compile(self, **kwargs):
        return SchemaCompiler(**kwargs)(self)

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)


class AnnotatedSchema(dict):
    def __init__(self, parent, **annotations):
        self.parent = parent
        super().__init__(annotations)


class RefPolicy(str, Enum):
    ALWAYS = "always"
    NOREPEAT = "norepeat"
    MINIMAL = "minimal"
    NEVER = "never"


class SchemaCompiler(Medley):
    ref_policy: RefPolicy = RefPolicy.NOREPEAT
    root: bool = True

    def __post_init__(self):
        self.refs = {}
        self.defs = {}
        self.done = set()
        self.name_indexes = Counter()

    def unique_name(self, t: type):
        name = t.__name__
        idx = self.name_indexes[name]
        self.name_indexes[name] += 1
        if idx > 0:
            name = f"{name}{idx + 1}"
        return name

    def __call__(self, x: object):
        rval = recurse(x, ("#",))
        if self.root:
            rval["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        if self.defs:
            rval["$defs"] = self.defs
        return rval

    def __call__(self, d: dict, pth: tuple):
        return {k: recurse(v, (*pth, k)) for k, v in d.items()}

    def __call__(self, xs: list, pth: tuple):
        return [recurse(x, (*pth, str(i))) for i, x in enumerate(xs)]

    def __call__(self, x: object, pth: tuple):
        return x

    def __call__(self, x: Schema, pth: tuple):
        is_always = self.ref_policy == RefPolicy.ALWAYS
        if x.get("type", "object") != "object":
            return call_next(x, pth)
        elif x in self.refs:
            if x not in self.done and self.ref_policy == RefPolicy.NEVER:
                raise Exception("Recursive schema cannot be compiled without $ref")
            elif x not in self.done or self.ref_policy not in (RefPolicy.NEVER, RefPolicy.MINIMAL):
                return {"$ref": "/".join(self.refs[x])}
            else:
                return call_next(x, pth)
        else:
            if is_always:
                name = self.unique_name(x.for_type)
                pth = ("#", "$defs", name)
            self.refs[x] = pth
            rval = call_next(x, pth)
            if "$ref" not in rval:
                self.done.add(x)
            if is_always:
                self.defs[name] = rval
                return {"$ref": f"#/$defs/{name}"}
            return rval

    def __call__(self, x: AnnotatedSchema, pth: tuple):
        rval = recurse(x.parent, pth)
        return {**rval, **x}
