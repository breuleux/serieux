import re
from dataclasses import field

from ovld import Medley, call_next, ovld, recurse
from ovld.dependent import Regexp

from ..ctx import AccessPath
from .lazy import LazyProxy


class Variables(AccessPath):
    refs: dict[tuple[str, ...], object] = field(default_factory=dict)

    def evaluate_reference(self, ref):
        def try_int(x):
            try:
                return int(x)
            except ValueError:
                return x

        stripped = ref.lstrip(".")
        dots = len(ref) - len(stripped)
        root = () if not dots else self.access_path[:-dots]
        parts = [try_int(x) for x in stripped.split(".")]
        return self.refs[(*root, *parts)]


class VariableInterpolation(Medley):
    @ovld(priority=3)
    def deserialize(self, typ: type[object], value: object, ctx: Variables):
        rval = call_next(typ, value, ctx)
        ctx.refs[ctx.access_path] = rval
        return rval

    @ovld(priority=2)
    def deserialize(self, typ: type[object], value: Regexp[r"^\$\{[^}]+\}$"], ctx: Variables):
        expr = value.lstrip("${").rstrip("}")

        def interpolate():
            value = ctx.evaluate_reference(expr)
            return recurse(typ, value, ctx)

        return LazyProxy(interpolate)

    @ovld(priority=1)
    def deserialize(self, typ: type[object], value: Regexp[r"\$\{[^}]+\}"], ctx: Variables):
        def interpolate():
            def repl(match):
                return str(ctx.evaluate_reference(match.group(1)))

            subbed = re.sub(r"\$\{([^}]+)\}", repl, value)
            return recurse(typ, subbed, ctx)

        return LazyProxy(interpolate)


# Add as a default feature in serieux.Serieux
__default_features__ = VariableInterpolation
