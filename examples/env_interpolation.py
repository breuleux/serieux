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
    """Context for environment variable interpolation."""

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
        """Deserialize environment variable to string."""
        return obj.value

    def deserialize(self, t: type[bool], obj: EnvValue, ctx: EnvContext):
        """Deserialize environment variable to bool."""
        value = obj.value.lower()
        if value in ("true", "1", "yes", "on"):
            return True
        elif value in ("false", "0", "no", "off"):
            return False
        raise ValidationError("Environment variable value cannot be converted to bool")

    def deserialize(self, t: type[int] | type[float], obj: EnvValue, ctx: EnvContext):
        """Deserialize environment variable to int."""
        try:
            return t(obj.value)
        except ValueError:
            raise ValidationError(
                f"Environment variable value cannot be converted to {t.__name__}"
            )

    def deserialize(self, t: type[list[object]], obj: EnvValue, ctx: EnvContext):
        """Deserialize environment variable to list of any supported type."""
        element_type = get_args(t)[0]
        return [
            recurse(element_type, EnvValue(item.strip()), ctx) for item in obj.value.split(",")
        ]


#################
# Demonstration #
#################


def main():
    # Set up test environment variables
    os.environ["DEBUG"] = "true"
    os.environ["PORT"] = "8080"
    os.environ["PI"] = "3.14159"
    os.environ["NAMES"] = "alice,bob,charlie"
    os.environ["NUMBERS"] = "1,2,3,4,5"
    os.environ["FLOATS"] = "1.1,2.2,3.3"

    # Create context with environment variables
    ctx = EnvContext()

    # Test boolean deserialization
    debug = deserialize(bool, "$DEBUG", ctx)
    assert debug is True
    print(f"Debug mode: {debug}")

    # Test integer deserialization
    port = deserialize(int, "$PORT", ctx)
    assert port == 8080
    print(f"Port: {port}")

    # Test float deserialization
    pi = deserialize(float, "$PI", ctx)
    assert abs(pi - 3.14159) < 0.00001
    print(f"Pi: {pi}")

    # Test list of strings deserialization
    names = deserialize(list[str], "$NAMES", ctx)
    assert names == ["alice", "bob", "charlie"]
    print(f"Names: {names}")

    # Test list of integers deserialization
    numbers = deserialize(list[int], "$NUMBERS", ctx)
    assert numbers == [1, 2, 3, 4, 5]
    print(f"Numbers: {numbers}")

    # Test list of floats deserialization
    floats = deserialize(list[float], "$FLOATS", ctx)
    assert floats == [1.1, 2.2, 3.3]
    print(f"Floats: {floats}")


if __name__ == "__main__":
    main()
