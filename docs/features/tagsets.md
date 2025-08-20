
# Tagged unions

A tagged union is a union of various types, differentiated using a tag. Serieux supports a wide variety of tagged unions, the simplest of which is, well, `TaggedUnion`:

```python
from serieux import TaggedUnion

serialize(TaggedUnion[Point, Person], Point(1, 2))
# => {"$class": "Point", "x": 1, "y": 2}
serialize(TaggedUnion[Point, Person], Person("Bob"))
# => {"$class": "Person", "name": "bob"}

deserialize(TaggedUnion[Point, Person], {"$class": "Point", "x": 1, "y": 2})
# => Point(1, 2)
```

If one of the types of the union is serialized as a primitive type, it will be stored in the special `$value` field:

```python
serialize(TaggedUnion[int, str], 42)  # => {"$class": "int", "$value": 42}
deserialize(TaggedUnion[int, str], {"$class": "str", "$value": "hello"})  # => "hello"
```

By default, serieux uses the type's name as a tag, but you can override this:

```python
from typing import Annotated
from serieux import Tagged

PoP = Tagged[Point, "dot"] | Tagged[Person, "dude"]

serialize(PoP, Point(1, 2))
# => {"$class": "dot", "x": 1, "y": 2}
```


## TagDict

Alternatively, you can define a mapping between names and types using `TagDict` and annotate types with it:

```python
from serieux import TagDict

td = TagDict({"dot": Point, "dude": Person})

serialize(Annotated[Any, td], Point(1, 2))
# => {"$class": "dot", "x": 1, "y": 2}
```

One advantage of `TagDict` over `TaggedUnion` is that it isn't fixed. You can dynamically register types into a `TagDict`.


## Referenced

If you want to be able to tag *any* class in any installed module, you can annotate with `Referenced`:

```python
from serieux import Referenced

serialize(Annotated[Any, Referenced], Point(1, 2))
# => {"$class": "my_module:Point", "x": 1, "y": 2}

serialize(Annotated[Any, Referenced], 1234)
# => {"$class": "builtins:int", "$value": 1234}
```

!!!warning
    `Referenced` is **not secure**, because the appropriate `$class` could be used by an attacker to execute pretty much any code. Do not use it to deserialize data you do not trust fully.

You can provide a default and default module to `Referenced`, e.g. `Annotated[Any, Referenced(MyType, "my_module")]` will default to `MyType` if there is no `$class` field and will look up symbols in `my_module` by default.


## FromEntryPoint

You can use Python's [entry points feature](https://docs.python.org/3/library/importlib.metadata.html#entry-points) to declare plugins and extensions. Serieux can use such an entry point to populate a tag mapping, which is useful if you want to define a serializable plugin system that third party packages can extend.

Suppose you have defined an entry point in `pyproject.toml` as follows, and have installed the package.

!!!important
    You need to pip install/uv sync the project after defining the entry points in order for them to be available. Otherwise they won't be found and you'll be confused.

```toml
[project.entry-points."some_namespace.animals"]
cat = "some_module:Cat"
```

Then `cat` will become an available tag for `FromEntryPoint("my_package.animals")`, which you can use like this:

```python
from serieux import FromEntryPoint

deserialize(Annotated[Animal, FromEntryPoint("some_namespace.animals")], {"$class": cat, ...})
# * Will look up an entry called "cat" in the entry point "my_namespace.animals"
# * Will also restrict the scope to subclasses of Animal.
```

## Custom

Use this template to define your own tagging systems.

```python
from serieux.features.tagset import TagSet

@dataclass(frozen=True)
class FromEntryPoint(TagSet):
    # Define some fields here

    def get_type(self, tag: str | None, ctx: Context) -> type:
        # Return the type associated to a tag. If $class is not provided, tag is None
        # and you can return a default class or raise an exception.
        ...

    def get_tag(self, t: type, ctx: Context) -> str | None:
        # Return the tag associated to the type (for serialization). If None is returned,
        # then $class will be omitted (should be consistent with get_type(None)).
        ...

    def closed(self, base):
        # Return True if the set of tags that are a subclass of base can be enumerated
        # The default implementation returns True
        # Note: make sure to handle the case where base is Any
        ...

    def iterate(self, base: type, ctx: Context = None) -> Iterable[tuple[str | None, type]]:
        # yield (tag, type) tuples corresponding to all possible tag/tuple pairs
        # This is used by schema and the definition of subparsers for the CLI
        # If that set cannot be enumerated (e.g. Referenced could be anything), this
        # iterator does not need to be exhaustive and can even be empty, but closed(base)
        # must return False.
        ...
```
