
# Basic usage

Serieux operates on standard dataclasses through the `serialize` and `deserialize` functions. It also supports a wide range of basic Python types, including:

* **Basic datatypes:** `int`, `float`, `str`, `bool`, `None`
* **Collections:** `list`, `tuple`, `dict`, `set`, `frozenset`
* **Dates and times:** `datetime`, `date`, `timedelta`
* **Others:** `Enum`, `Path`, `Literal`, `Any`, `Annotated`, `Union`, `Optional`

The first argument to `serialize` and `deserialize` is always the *intended* type to serialize from or deserialize to (which may be annotated with extra directives). The second argument is the data to transform. The third argument is the Context. In general you will only pass that argument to enable certain features such as variable interpolation.


## Serialization

```python
from serieux import serialize

@dataclass
class Person:
    # Name of the person
    name: str
    # Age of the person
    age: int

serialize(Person, Person("Bob", 40))
# => {"name": "Bob", "age": 40}
```

## Deserialization

```python
from serieux import deserialize

deserialize(Person, {"name": "Bob", "age": 40})
# => Person(name="Bob", age=40)
```

## Load from a file

Use a `Path` anywhere in the data structure to deserialize to fetch data from that file.

```python
deserialize(Person, Path("person.yaml"))

# The paths can be nested in a data structure no problem
deserialize(dict[str, Person], {"olivia": Path("olivia.yaml"), "john": Path("john.yaml")})
```

## Save to a file

Purely for convenience, you can use the `dump` function to save to a file.

```python
from serieux import dump

dump(Person, Person(name="Harold", age=8) dest=Path("person.yaml"))
```

## Merging multiple sources

```python
from serieux import deserialize, Sources

deserialize(Person, Sources({"name": "Barb"}, {"age": 75}, {"age": 78}))
# => Person(name="Barb", age=78)

deserialize(
    dict[str, Person],
    Sources(
        {"liv": {"name": "Olivia"}, "kev": {"name": "Kevin"}},
        {"liv": {"age": 30}, "kev": {"age": 25}},
    )
)
# => {
#      "liv": Person(name="Olivia", age=30),
#      "kev": Person(name="Kevin", age=25)
#    }
```

Use the following pattern to merge together default values, the config, and overrides.

```python
deserialize(
    Config,
    Sources(
        Path("defaults.yaml"),
        Path("config.yaml"),
        Path("overrides.yaml"),
    )
)
```

[**Read more.**](./features/multi.md)

## Interpolation

Variable interpolation is not a default feature. You need to pass `Environment()` as the third argument (the context) in order to enable it.

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

[**Read more.**](./features/interpol.md)


## Environment variables

Insert environment variables with the `${env:VAR}` interpolation.

```python
deserialize(
    Person,
    {"name": "${env:PERSON_NAME}", "age": "${env:PERSON_AGE}"},
    Environment()
)
```


## Command-line parsing

```python
from serieux import CommandLineArguments

deserialize(Person, CommandLineArguments(["--name", "Cora", "--age", "19"]))
# => Person(name="Cora", age=19)
```

## Unions

Serieux supports most unions, but it must be able to differentiate the possible members either by their fields or serialized type:

```python
@dataclass
class Point:
    x: int
    y: int

print(deserialize(Person | Point, {"x": 1, "y": 2}))
# => Point(x=1, y=2)

print(deserialize(Person | Point, {"name": "Alice", "age": 30}))
# => Person(name="Alice", age=30)
```


## Tagged unions

Serieux also supports differentiating union members through the special `$class` configuration field, but this must be enabled by using a `TaggedUnion`. In the following example, this is necessary, because Person and Monster have the same fields and could not be differentiated other than with an explicit tag.

```python
@dataclass
class Monster:
    name: str
    age: int

PoM = TaggedUnion[Person, Monster]

print(serialize(PoM, Person(name="Alice", age=30)))
# => {"$class": "person", "name": "Alice", "age": 30}

print(deserialize(PoM, {"$class": "person", "name": "Alice", "age": 30}))
# => Person(name="Alice", age=30)

print(deserialize(PoM, {"$class": "monster", "name": "Floborb", "age": 37154}))
# => Monster(name="Floborb", age=37154)
```

[**Read more.**](./features/tagsets.md)


## Schemas

You can easily generate a JSON schema from any type with `serieux.schema(T).compile()`. Proper documentation for each field will also be included automatically.

```python
from serieux import schema

print(schema(Person).compile())
# {
#     "type": "object",
#     "properties": {
#         "name": {
#             "type": "string",
#             "description": "Name of the person"
#         },
#         "age": {
#             "type": "integer",
#             "description": "Age of the person"
#         }
#     },
#     "required": ["name", "age"],
#     "$schema": "https://json-schema.org/draft/2020-12/schema"
# }
```

`Schema.compile` takes two optional arguments to customize how the schema is presented:

* **`root`**: if True, will set the `$schema` key.
* **`ref_policy`**: control how `$ref` is used in the output schema.
    * **`"always"`**   Use $ref for all objects
    * **`"norepeat"`** Use $ref only for repeated objects (default)
    * **`"minimal"`**  Use $ref only when necessary to break recursion
    * **`"never"`**    Never use $ref (will fail on recursive types)

!!!note
    It's an always changing landscape, but e.g. some LLM interfaces that allow specifying an output schema will refuse refs. In that case you should pass `ref_policy="never"`.
