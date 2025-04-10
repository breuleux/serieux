import os
from dataclasses import dataclass, field
from typing import get_args

from ovld import Medley, recurse
from ovld.dependent import Regexp

from serieux import Context, Serieux, deserialize
from serieux.exc import ValidationError

##################
# Implementation #
##################


@dataclass
class EnvValue:
    value: str


@dataclass
class EnvContext(Context):
    environ: dict[str, str] = field(default_factory=lambda: os.environ)


@Serieux.extend
class EnvInterpolator(Medley):
    """Custom serializer that interpolates environment variables in strings."""

    def deserialize(self, t: type[object], obj: Regexp[r"^\$[A-Z_][A-Z0-9_]*$"], ctx: EnvContext):
        var_name = obj.lstrip("$")
        value = ctx.environ.get(var_name)
        if value is None:
            raise ValidationError(f"Environment variable {var_name} not found")
        return recurse(t, EnvValue(value), ctx)

    def deserialize(self, t: type[str], obj: EnvValue, ctx: EnvContext):
        return obj.value

    def deserialize(self, t: type[bool], obj: EnvValue, ctx: EnvContext):
        value = obj.value.lower()
        if value in ("true", "1", "yes", "on"):
            return True
        elif value in ("false", "0", "no", "off"):
            return False
        raise ValidationError("Environment variable value cannot be converted to bool")

    def deserialize(self, t: type[int] | type[float], obj: EnvValue, ctx: EnvContext):
        try:
            return t(obj.value)
        except ValueError:
            raise ValidationError(
                f"Environment variable value cannot be converted to {t.__name__}"
            )

    def deserialize(self, t: type[list[object]], obj: EnvValue, ctx: EnvContext):
        element_type = get_args(t)[0]
        return [
            recurse(element_type, EnvValue(item.strip()), ctx) for item in obj.value.split(",")
        ]


#################
# Demonstration #
#################


def main():
    os.environ["DEBUG"] = "true"
    os.environ["PORT"] = "8080"
    os.environ["PI"] = "3.14159"
    os.environ["NAMES"] = "alice,bob,charlie"
    os.environ["FLOATS"] = "1.1,2.2,3.3"

    ctx = EnvContext()

    debug = deserialize(bool, "$DEBUG", ctx)
    print(f"Debug mode: {debug}")
    assert debug is True

    port = deserialize(int, "$PORT", ctx)
    print(f"Port: {port}")
    assert port == 8080

    pi = deserialize(float, "$PI", ctx)
    print(f"Pi: {pi}")
    assert abs(pi - 3.14159) < 0.00001

    names = deserialize(list[str], "$NAMES", ctx)
    print(f"Names: {names}")
    assert names == ["alice", "bob", "charlie"]

    numbers = deserialize(list[int], [1, 2, "$PORT"], ctx)
    print(f"Numbers: {numbers}")
    assert numbers == [1, 2, 8080]

    floats = deserialize(list[float], "$FLOATS", ctx)
    print(f"Floats: {floats}")
    assert floats == [1.1, 2.2, 3.3]


if __name__ == "__main__":
    main()
