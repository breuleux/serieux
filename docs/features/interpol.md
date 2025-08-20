# Variable interpolation

`serieux` supports variable interpolation, but not as a default feature. You need to pass `Environment()` as the third argument (the context) in order to enable it.

The default interpolation syntax is `${xyz}`.

```python
from serieux import Environment

@dataclass
class Court:
    king: Person
    jester: Person

deserialize(
    Court,
    {
        "king": {"name": "Archibald", "age": 50},
        "jester": {"name": "Funnier than ${king.name}", "age": 23}
    },
    Environment()
)
# => Court(
#      king=Person(name="Archibald", age=50),
#      jester=Person(name="Funnier than Archibald", age=23)
#    )
```

* Interpolation starts from the root.
* A pattern starting with a dot, e.g. `${.name}` looks for name at the same nesting level.
* Refer to variables from the parent with `${..name}`, and so on.

You can set extra values in the environment if needed:

```python
env = Environment()
env["exclaim"] = "wow"
env["person", "name"] = "Gerald"

assert deserialize(str, "${exclaim} ${person.name}", env) == "wow Gerald"
```

## Environment variables

Use `${env:VARIABLE}` to pull an environment variable.

```python
import os

os.environ["PERSON_NAME"] = "Olivia"
os.environ["PERSON_AGE"] = "31"

deserialize(
    Person,
    {"name": "${env:PERSON_NAME}", "age": "${env:PERSON_AGE}"},
    Environment()
)
# => Person(name="Olivia", age=31)
```

## Custom syntax

You can customize the pattern used for variable interpolation by passing a regular expression to the `interpolation_pattern` argument of `Environment`. That regex must have **one** capture group that captures the expression (that is, it must exclude the delimiters).

For example, if you want to interpolate using `~xyz` instead of `${xyz}`, do this:

```python
deserialize(Point, {"x": 12, "y": "~x"}, Environment(interpolation_pattern=r"~([a-z]+)"))
# => Point(12, 12)
```

## Custom resolvers

You can subclass `Environment` to add custom resolvers. Note that implementations of the `resolve_variable` method stack on each other. You can define it multiple times.

```python
from typing import Any, Literal

class EvalEnvironment(Environment):
    def resolve_variable(self, t: Any, method: Literal["eval"], expr: str, /):
        return eval(expr)

deserialize(int, "${eval:2 + 2}", EvalEnvironment())
# => 4
```

!!!note
    Match on `method: Literal[""]` to override the default interpolation behavior.

The first argument, `t`, is the type of the field we're trying to interpolate to. It's not typically needed, but you can dispatch on it if needed for some reason.
