---
name: serieux
description: Use serieux for serialization/deserialization in Python. Trigger when the user imports serieux, wants to serialize/deserialize dataclasses, load/dump config files, generate JSON schemas, use variable interpolation, tagged unions, command-line parsing, or create custom serialization features.
---

# serieux — Serialization / Deserialization for Python

`serieux` converts between Python objects and JSON-compatible data (dicts/lists/primitives), YAML, TOML, and files. It is built on `ovld.Medley` for composable, type-dispatched serialization.

## Core usage

```python
from dataclasses import dataclass
from serieux import serialize, deserialize

@dataclass
class Person:
    # Name of the person
    name: str
    # Age of the person
    age: int

serialize(Person, Person("Bob", 40))
# => {"name": "Bob", "age": 40}

deserialize(Person, {"name": "Bob", "age": 40})
# => Person(name="Bob", age=40)
```

Supported built-in types: `int`, `float`, `str`, `bool`, `None`, `list`, `tuple`, `dict`, `set`, `frozenset`, `datetime`, `date`, `timedelta`, `Enum`, `Path`, `Literal`, `Any`, `Annotated`, `Union`, `Optional`.

## Load from a file

Pass a `Path` anywhere in the data structure — serieux loads and parses the file automatically (JSON, YAML, TOML detected by extension):

```python
from pathlib import Path

deserialize(Person, Path("person.yaml"))

# Works nested too
deserialize(dict[str, Person], {"alice": Path("alice.yaml"), "bob": Path("bob.yaml")})
```

## Save to a file

```python
from serieux import dump

dump(Person, Person(name="Harold", age=8), dest=Path("person.yaml"))
```

## Merging multiple sources

`Sources` merges inputs left-to-right; later sources take precedence:

```python
from serieux import Sources

deserialize(Person, Sources({"name": "Barb"}, {"age": 75}, {"age": 78}))
# => Person(name="Barb", age=78)

# Typical pattern: defaults → config → overrides
deserialize(Config, Sources(Path("defaults.yaml"), Path("config.yaml"), Path("overrides.yaml")))
```

## Variable interpolation

Pass `Environment()` as the context argument to enable `${variable}` syntax:

```python
from serieux import Environment

deserialize(
    Court,
    {"king": {"name": "Archibald", "age": 50},
     "jester": {"name": "Funnier than ${king.name}", "age": 23}},
    Environment()
)
```

- `${.name}` — same level
- `${..name}` — parent level
- `${env:VAR}` — environment variable
- Custom resolvers: subclass `Environment` and override `resolve_variable(t, method, expr)`

## Command-line parsing

```python
from serieux import CommandLineArguments

deserialize(Person, CommandLineArguments(["--name", "Cora", "--age", "19"]))
# => Person(name="Cora", age=19)
```

Use `Auto[func]` to deserialize into a callable partial, or `Call[func]` to call immediately. Add `[alias: -a]` or `[action: append]` in field comments to customize CLI behavior.

## Unions

Serieux differentiates union members by their fields or serialized type:

```python
deserialize(Person | Point, {"x": 1, "y": 2})   # => Point(x=1, y=2)
deserialize(Person | Point, {"name": "Alice", "age": 30})  # => Person(...)
```

## Tagged unions

Use `TaggedUnion` when types can't be auto-differentiated (e.g. same field names). A `$class` field is added:

```python
from serieux import TaggedUnion, Tagged

PoM = TaggedUnion[Person, Monster]

serialize(PoM, Person(name="Alice", age=30))
# => {"$class": "person", "name": "Alice", "age": 30}

deserialize(PoM, {"$class": "monster", "name": "Floborb", "age": 37154})
# => Monster(...)
```

Override the tag: `Tagged[MyClass, "custom_tag"]`.
Dynamic tag maps: `TagDict` (mapping of tag → type).
Plugin systems: `FromEntryPoint`.

## JSON Schema generation

```python
from serieux import schema

schema(Person).compile()
# {"type": "object", "properties": {"name": {...}, "age": {...}}, "required": [...], "$schema": "..."}

# Options
schema(Person).compile(root=False, ref_policy="never")
```

`ref_policy` values: `"always"`, `"norepeat"` (default), `"minimal"`, `"never"`.
Use `"never"` for LLM tool-call schemas that don't support `$ref`.

## Pydantic integration

```python
import serieux.pycompat  # enable once; Pydantic BaseModel support is automatic after this
```

## Custom serialization — classmethods

Add classmethods to your type. `call_next` falls back to default behavior.

```python
@dataclass
class RGB:
    red: int
    green: int
    blue: int

    # Simplest: string ↔ object
    @classmethod
    def serieux_to_string(cls, obj):
        return f"#{obj.red:02x}{obj.green:02x}{obj.blue:02x}"

    @classmethod
    def serieux_from_string(cls, s):
        h = s.lstrip("#")
        return cls(int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))

    # Full control (optional):
    @classmethod
    def serieux_deserialize(cls, obj, ctx, call_next):
        if isinstance(obj, str):
            return cls.serieux_from_string(obj)
        return call_next(cls, obj, ctx)

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        return cls.serieux_to_string(obj)

    @classmethod
    def serieux_schema(cls, ctx, call_next):
        return {"oneOf": [{"type": "string", "pattern": r"^#[0-9a-fA-F]{6}$"}, call_next(cls, ctx)]}
```

For rich field-based models, implement `serieux_model` returning a `Model`:

```python
from serieux import Field, Model

@classmethod
def serieux_model(cls, call_next):
    return Model(
        original_type=cls,
        constructor=cls,
        fields=[
            Field(name="red", type=int, description="Red level",
                  serialized_name="R", argument_name="reddie", property_name="red"),
            # ...
        ],
        from_string=rgb_from_string,
        to_string=rgb_to_string,
        regexp=r"^#[0-9a-fA-F]{6}$",
        string_description="A RGB color in hex, such as #ff0000",
    )
```

- `property_name=None` → field is not serialized
- `argument_name=None` → field is not deserialized

## model() — inspecting and extending the type model

`model(t)` returns a `Model` describing how serieux handles a type, or `None` if the type is not supported. It is the backbone of serialization: all built-in types (dataclasses, lists, dates, …) are handled by registered `model()` overloads.

```python
from serieux import model

m = model(Person)
# Model(original_type=Person, fields=[...], constructor=Person, ...)
```

### Model fields

| Field | Type | Meaning |
|-------|------|---------|
| `original_type` | `type` | The type this model describes |
| `fields` | `list[Field] \| None` | Field list for dict-like types; `None` for non-field types |
| `element_field` | `Field \| None` | Single element field for list-like types |
| `constructor` | `Callable \| None` | Called with deserialized kwargs to build the object |
| `from_list` | `Callable \| None` | Called with a list of elements (list-like types) |
| `to_list` | `Callable` | Converts object to list for serialization (default: `list`) |
| `from_string` | `Callable \| None` | Parses string → object; enables string deserialization |
| `to_string` | `Callable \| None` | Converts object → string; when set, string form is preferred |
| `regexp` | `re.Pattern \| None` | Validates string form; included in JSON schema |
| `string_description` | `str \| None` | Human-readable description of the string format |
| `allow_extras` | `bool` | If `True`, unknown keys in dicts are silently ignored |

### Field fields

| Field | Type | Meaning |
|-------|------|---------|
| `name` | `str` | Canonical field name |
| `type` | `type` | Field type |
| `description` | `str \| None` | Docstring / description (used in JSON schema) |
| `metadata` | `dict` | Arbitrary metadata from dataclass field / docstring |
| `default` | `object` | Default value (`MISSING` if none) |
| `default_factory` | `Callable` | Default factory (`MISSING` if none) |
| `argument_name` | `str \| int` | Name (or positional index) used when calling `constructor`; `None` = skip |
| `property_name` | `str \| None` | Attribute name read during serialization; `None` = not serialized |
| `serialized_name` | `str` | Key name in the serialized dict |
| `metavar` | `str \| None` | CLI help metavar |
| `required` | `bool` (property) | `True` when no default and no default_factory |

### Type predicates

```python
from serieux import Modelizable, StringModelizable, FieldModelizable, ListModelizable

Modelizable(Person)       # True — has a Model
FieldModelizable(Person)  # True — Model has .fields
StringModelizable(date)   # True — Model has .from_string
ListModelizable(list[int])# True — Model has .element_field
```

These are `ovld` class-checks, usable as type annotations in dispatch signatures.

### Extending model() for new types

Register new overloads of `model` exactly like any other `ovld` function:

```python
from ovld import ovld
from serieux import model, Model, Field

@ovld
def model(t: type[MyClass]):
    return Model(
        original_type=t,
        constructor=MyClass,
        fields=[
            Field(name="x", type=int),
            Field(name="y", type=int),
        ],
    )
```

For a string-only type:

```python
@ovld
def model(t: type[MyStringType]):
    return Model(
        original_type=t,
        from_string=MyStringType.parse,
        to_string=str,
        regexp=r"^\d+$",
        string_description="A non-negative integer string",
    )
```

### allow_extras via SerieuxConfig

To silently ignore unknown keys on a dataclass, set `allow_extras` on an inner `SerieuxConfig` class (or use `AllowExtras` as an annotation):

```python
from serieux import AllowExtras
from typing import Annotated

@dataclass
class Flexible:
    name: str

    class SerieuxConfig:
        allow_extras = True

# or via annotation:
deserialize(Annotated[Flexible, AllowExtras], {"name": "Bob", "extra": "ignored"})
```

### field_at — navigate to a field by path

```python
from serieux import field_at

field_at(Court, "king.name")
# Field(name="name", type=str, ...)
```

Supports dotted paths into nested dataclasses, dicts, lists, and unions.

## Advanced features — which abstraction to use

Serieux has four extension points. Pick based on *where* the behaviour is controlled:

| What you need | Use |
|---|---|
| Change how a **specific type** is serialized/deserialized | `model.register` overload or `serieux_*` classmethods |
| Annotate individual **fields or types** with extra metadata that affects their handling | **Instruction** |
| Carry **call-site configuration or shared state** across an entire traversal | **Context** subclass |
| Add cross-cutting dispatch rules that activate based on type and/or context | **Medley** |

These are not mutually exclusive: a feature typically defines an Instruction (what to opt-in with), a Context (optional call-site configuration), and a Medley (the dispatch rules that tie them together).

## Instructions

An `Instruction` is a type annotation marker: `Annotated[MyType, MyInstruction]`, written concisely as `MyType @ MyInstruction`. Dispatch rules can match on it with `type[Any @ MyInstruction]`.

**Use an Instruction when** the feature is opted-in per-field or per-type in the type annotation rather than at the call site.

### Singleton instruction (no data)

```python
from serieux.instructions import Instruction, T
from typing import TYPE_CHECKING, Annotated, TypeAlias

if TYPE_CHECKING:
    # Makes type checkers treat it as a transparent alias
    MyFlag: TypeAlias = Annotated[T, None]
else:
    MyFlag = Instruction("MyFlag", annotation_priority=1, inherit=False)
```

- `annotation_priority` controls ordering when multiple annotations stack on a type.
- `inherit=False` — the annotation stays on the annotated type only.
- `inherit=True` — the annotation propagates into each field's type and down into union members (used by `DeepLazy`, `CommentRec`).

### Instruction with data (BaseInstruction subclass)

When the instruction needs to carry configuration use a frozen dataclass subclassing `BaseInstruction`:

```python
from dataclasses import dataclass
from serieux.instructions import BaseInstruction

@dataclass(frozen=True)
class Encrypted(BaseInstruction):
    algorithm: str = "fernet"
    inherit: bool = False   # whether to push down into fields
```

Usage: `Annotated[str, Encrypted(algorithm="aes")]` or `str @ Encrypted()`.

### Dispatching on an instruction

```python
from typing import Any
from ovld import ovld
from serieux.instructions import strip   # remove instruction from type

class MyFeature(Medley):
    @ovld(priority=HIGH)
    def deserialize(self, t: type[Any @ MyFlag], obj: object, ctx: Context):
        base_type = MyFlag.strip(t)   # the type without the annotation
        ...
        return recurse(base_type, obj, ctx)
```

### Decomposing an instruction with data

```python
@ovld(priority=HIGH)
def deserialize(self, t: type[Any @ Encrypted], obj: str, ctx: Context):
    base_type, instr = Encrypted.decompose(t)
    # instr is the Encrypted instance with its data fields
    # base_type is the underlying type
    return decrypt(obj, instr.algorithm)
```

Key helpers (all on the instruction class):
- `MyInstr.extract(t)` → the instruction instance (or `None`)
- `MyInstr.extract_all(t)` → iterator of all matching instances
- `MyInstr.strip(t)` → type without the instruction
- `MyInstr.decompose(t)` → `(stripped_type, instance)` — the common pattern

### Extending model() for an instruction

If your instruction changes how a type maps to a Model, register on `model` directly:

```python
from serieux import model, Model
from serieux.instructions import strip

@model.register
def _(t: type[Any @ MyFlag]):
    base = strip(t, MyFlag)
    m = call_next(base)   # get the normal model
    # ... modify m ...
    return m
```

This is how `Partial` and `AllowExtras` work: they intercept model-building for annotated types.

## Creating new features (Medley-based)

A Medley adds dispatch rules that become active when the Medley is composed into the serializer. Compose with `+` at the call site or permanently via `Serieux.extend`.

```python
from ovld import Medley, ovld
from ovld.dependent import Regexp
from serieux import serieux, Context, ValidationError
from serieux.priority import LOW

class EvalFeature(Medley):
    @ovld(priority=LOW)
    def deserialize(self, t: type[object], obj: Regexp["^="], ctx: Context):
        value = eval(obj[1:])
        if not isinstance(value, t):
            raise ValidationError("Wrong type")
        return value

eserieux = serieux + EvalFeature()
eserieux.deserialize(int, "=3*2")   # => 6
```

Key rules:
- **Always set a priority** on every `serialize`/`deserialize`/`schema` method — without one, ovld may raise an `AmbiguityError`.
- Priority levels live in `serieux.priority`, not in `serieux` directly.
- Use `recurse` (not the function name) for recursive calls within a Medley.
- Use `call_next` to delegate to lower-priority overloads.
- Methods that require a specific context type in their signature are silently skipped when that context is absent — use this to make features opt-in.
- To make a feature active by default globally: `Serieux.extend(EvalFeature)`.

### Medley inheritance

Medleys can subclass each other to layer behaviour. `IncludeFile` extends `FromFile`, which extends `PartialBuilding` — each layer adds more dispatch rules without touching the others:

```python
class BaseFeature(Medley):
    @ovld(priority=STD)
    def deserialize(self, t: Any, obj: MyType, ctx: Context):
        ...

class ExtendedFeature(BaseFeature):
    # Inherits all rules from BaseFeature and adds new ones
    @ovld(priority=HIGH)
    def deserialize(self, t: Any, obj: MyType, ctx: SpecialContext):
        ...
```

### Combining Instructions + Medley (full pattern)

The typical real feature defines an Instruction for type-level opt-in, then a Medley with rules that dispatch on that Instruction:

```python
from dataclasses import dataclass
from serieux.instructions import BaseInstruction
from serieux.priority import HI3

@dataclass(frozen=True)
class Validated(BaseInstruction):
    min_length: int = 0
    inherit: bool = False

class ValidationFeature(Medley):
    @ovld(priority=HI3)
    def deserialize(self, t: type[Any @ Validated], obj: str, ctx: Context):
        base, instr = Validated.decompose(t)
        result = recurse(base, obj, ctx)
        if len(result) < instr.min_length:
            raise ValidationError(f"Too short (min {instr.min_length})")
        return result

# Usage in a dataclass field:
@dataclass
class Form:
    name: Annotated[str, Validated(min_length=2)]
```

## Custom Context classes

`Context` is a `Medley` (so it's also composable with `+`). Subclass it to carry extra information or state into the dispatch machinery.

### Marker context (opt-in feature flag)

The simplest pattern: an empty subclass whose *presence* in the context activates a feature.

```python
from dataclasses import dataclass
from serieux import Context
from serieux.priority import HIGH
from ovld import Medley, ovld

class Verbose(Context):
    pass  # marker — no fields needed

class VerboseFeature(Medley):
    @ovld(priority=HIGH)
    def deserialize(self, t: type[object], obj: object, ctx: Verbose):
        print(f"deserializing {t} from {obj!r}")
        return call_next(t, obj, ctx)

vserieux = serieux + VerboseFeature()
vserieux.deserialize(int, 42, Verbose())   # prints, then returns 42
```

The method only fires when `Verbose` is part of the context; without it the method is invisible to dispatch.

### Context with configuration fields

Use dataclass-style fields (same as Medley fields) to pass configuration:

```python
from dataclasses import dataclass, field
from serieux import Context

class EncryptionKey(Context):
    password: str = None
```

Instantiate with `EncryptionKey(password="secret")` and compose: `Trail() + EncryptionKey(password="s")`.

### Context with mutable state

Context objects are **not mutated** (they behave like frozen dataclasses by default), but you can set a field to a mutable structure (e.g. a `dict`) and mutate *that* during traversal. This is how `Environment` accumulates resolved interpolation values, and how `Patcher` collects patches:

```python
from dataclasses import dataclass, field
from serieux import Context

class Collector(Context):
    # mutable dict — shared across the whole traversal
    seen: dict = field(default_factory=dict)

class CollectFeature(Medley):
    @ovld(priority=HIGH)
    def deserialize(self, t: type[object], obj: object, ctx: Collector):
        result = call_next(t, obj, ctx)
        ctx.seen[ctx.trail] = result   # mutate the shared dict
        return result
```

### Dispatching on context type

Combine context types in a method signature with `+` to require multiple contexts simultaneously:

```python
# Only fires when BOTH EncryptionKey and Patcher are present
@ovld(priority=PRIO)
def deserialize(self, t: type[Any @ Secret], obj: Any, ctx: EncryptionKey + Patcher):
    ctx.declare_patch(...)
    return recurse(Secret.strip(t), obj, ctx)
```

### Removing a context

Use `ctx - SomeContext` to strip a context from the composition before recursing:

```python
result = call_next(Secret.strip(t), obj, ctx - EncryptionKey)
```

### Context inheritance — extending an existing context

Subclass an existing Context to inherit its behaviour and add new dispatch methods. `Promptable` extends `Environment`, adding a `resolve_variable` overload for `${prompt:...}` syntax, while inheriting all of `Environment`'s interpolation logic:

```python
class Promptable(Environment):
    prompt_function: Callable = default_prompt

    @ovld
    def resolve_variable(self, t: Any, method: Literal["prompt"], expr: str, /):
        value = self.prompt_function(self, expr or "Enter value")
        return decode_string(t, value)
```

Context methods (like `resolve_variable`) use ovld internally — subclasses add new overloads that layer on top of the parent's.

### Trail — built-in path tracking

`Trail` tracks the current path through the object tree. Subclass it to get path tracking for free (as `Environment` and `Patcher` do):

```python
from serieux import Trail

# ctx.trail — tuple of field names / indices to the current node
# ctx.full_trail — tuple of (object_type, object, field_key) triples
# e.g. ctx.trail == ("king", "name") when inside Court.king.name
```

### Composing contexts at the call site

```python
from serieux import Trail, Environment

result = deserialize(Config, data, Trail() + Environment())
# or incrementally:
ctx = Trail()
if need_interpolation:
    ctx += Environment()
result = deserialize(Config, data, ctx)
```

## Priority reference

All priorities are in `serieux.priority`. Higher value = runs first.

```
MAX  = 100      # schema caching only
HI9…HI2 = 9…2  # named HI9, HI8, … HI2
HIGH = HI1 = 1
DEFAULT = 0
STD5 = -1
STD4 = -2
STD3 = -3
STD2 = -4
STD  = STD1 = -5
LOW  = LO1 = -11
LO2…LO5 = -12…-15
MIN  = -100     # last-resort error fallback
```

`PriorityLevel` supports `.next()` (derive one step tighter) and `(n)` (reserve a range): e.g. `HIGH(3).next()` = 4, `STD.next()` = -4.

### Built-in rule priorities (where to slot your own rules)

| Priority | What runs at this level |
|----------|------------------------|
| `MAX` (100) | Schema result caching (all types) |
| `HI6` (6) | `Comment`/`CommentRec` wrappers |
| `HI5` (5) | `Lazy`/`DeepLazy` unwrapping |
| `HI4` (4) | `Partial`, `Sources`, interpolation storage |
| `HI3` (3) | `TagSet` dispatch, interpolation string handling |
| `HI2` (2) | `ModifyContext` annotations, `FileBacked`, dotted-key flattening, `AutoRegistered` schema |
| `HIGH`/`HI1` (1) | File `$include` key handling |
| `DEFAULT` (0) | `fromfile` / `Path` loading (STD5.next()) |
| `STD2…STD` (-4…-5) | User `serieux_*` classmethods (`STD4.next()` = -6), encrypt/secret |
| `STD` (-5) | Standard built-ins: `str`, `int`, `float`, `bool`, `None`, `dict`, `list`, `Enum`, `Path`, `datetime`, `Literal`, `Union`, `FieldModelizable`, `ListModelizable` |
| `STD3` (-3) | `Enum` (slightly above STD) |
| `STD2` (-4) | `StringModelizable` |
| `LO4` (-14) | `object.__init__` generic fallback |
| `LO5` (-15) | `Indirect`/`TypeAliasType` unwrapping |
| `LOW`/`LO1` (-11) | `AutoTag` catch-all (`Exactly[object]`) |
| `MIN` (-100) | Error handler for `Any` (serialize/deserialize) |

**Practical guidance for new features:**
- Override a specific built-in → `HIGH` or `HI2`/`HI3`
- Extend without conflicting → `DEFAULT` (0) or between `HIGH` and `STD`
- Fallback / last resort → `LOW` or `MIN`

## Public API

```python
from serieux import (
    # Core
    serialize, deserialize, schema, load, dump,
    get_serializer, get_deserializer,
    # Registration decorators
    serializer, deserializer, schema_definition,
    # Model / field
    model, field_at, Model, Field, FieldModelizable, ListModelizable, Modelizable, StringModelizable,
    # Features / context
    Context, Auto, Lazy, DeepLazy, LazyProxy, Partial, Sources,
    Environment, CommandLineArguments, CLIDefinition, parse_cli,
    # Tagging
    Tagged, TaggedUnion, TaggedSubclass, ReferencedClass, Referenced, AutoRegistered,
    # File / config
    IncludeFile, AllowExtras, DottedNotation, WorkingDirectory, Patch, Patcher,
    # Schema
    RefPolicy, Schema, Trail,
    # Comments
    Comment, CommentRec,
    # Errors
    BaseSerieuxError, SerieuxError, ValidationError, SerieuxExceptionGroup,
    # The global serieux instance (extend with +)
    serieux,
)
```

Full docs are in `docs/` if needed.
