import json
from enum import Enum
from typing import Any, Counter

from ovld import Medley, call_next, recurse

from .features.partial import merge


class Schema:
    def __init__(self, t):
        self.for_type = t
        self.data = {}
        self.redirect = None

    def update(self, data):
        if isinstance(data, Schema):
            data = data.data
        if isinstance(data, dict):
            self.data.update(data)
        else:
            assert not self.data
            self.redirect = data

    def get(self, key, default):
        return self.data.get(key, default)

    def __contains__(self, key):
        return key in self.data

    def compile(self, **kwargs):
        return SchemaCompiler(**kwargs)(self)

    def json(self, fp=None):
        if fp:  # pragma: no cover
            return json.dump(self.compile(), fp, indent=4)
        else:
            return json.dumps(self.compile(), indent=4)


class AnnotatedSchema:
    def __init__(self, parent, **annotations):
        self.parent = parent
        self.data = annotations


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

    def unique_name(self, t: Any):
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
        if x.redirect:
            return recurse(x.redirect, pth)
        is_always = self.ref_policy == RefPolicy.ALWAYS
        if x.get("type", "object") != "object" or "oneOf" in x:
            return call_next(x.data, pth)
        elif x in self.refs:
            if x not in self.done and self.ref_policy == RefPolicy.NEVER:
                raise Exception("Recursive schema cannot be compiled without $ref")
            elif x not in self.done or self.ref_policy not in (RefPolicy.NEVER, RefPolicy.MINIMAL):
                return {"$ref": "/".join(self.refs[x])}
            else:
                return call_next(x.data, pth)
        else:
            if is_always:
                name = self.unique_name(x.for_type)
                pth = ("#", "$defs", name)
            self.refs[x] = pth
            rval = call_next(x.data, pth)
            if "$ref" not in rval:
                self.done.add(x)
            if is_always:
                self.defs[name] = rval
                return {"$ref": f"#/$defs/{name}"}
            return rval

    def __call__(self, x: AnnotatedSchema, pth: tuple):
        rval = recurse(x.parent, pth)
        return merge(rval, recurse(x.data, pth))
