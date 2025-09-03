
# Custom serialization

To customize serialization for a type, you can implement one or more of the following *classmethods*.

Typically [**`serieux_model`**](#serieux_model) should suffice in 90% of cases, because all other functionality can be derived from it. If you only need to map to and from a string representation, [**`serieux_to/from_string`**](#serieux_to_string) may be easier. The other three methods let you customize the representation precisely how you want it.

* [**`serieux_model(cls, call_next)`**](#serieux_model): returns a Model that defines fields, a constructor, and optionally string conversions. serialize/deserialize/schema can very efficiently handle types that have a model.
* [**`serieux_to_string(cls, obj)`**](#serieux_to_string): defines how to convert the object to a string.
* [**`serieux_from_string(cls, string)`**](#serieux_from_string): defines how to transform a string to an object.
* [**`serieux_deserialize(cls, data, ctx, call_next)`**](#serieux_deserialize): defines how to deserialize the data into an object.
* [**`serieux_serialize(cls, obj, ctx, call_next)`**](#serieux_serialize): defines how to serialize the object.
* [**`serieux_schema(cls, ctx, call_next)`**](#serieux_schema): returns a JSON schema corresponding to the object's representation.

When provided, the `call_next` argument can be used to call the default serialize/deserialize/schema.

## serieux_model

The `serieux_model` method returns a `Model` that defines fields, constructor, and string conversions. This is the most comprehensive approach and allows serieux to efficiently handle serialization, deserialization, and schema generation.

The following example is overwrought, in the sense that it shows the full interface, but `argument_name`, `property_name` and `serialized_name` default to the value of `name`, so you typically don't have to set them.

```python
from serieux import Field, Model

class RGB:
    def __init__(self, reddie, greenie, bluey):
        self.red = reddie
        self.green = greenie
        self.blue = bluey

    @classmethod
    def serieux_model(cls, call_next):
        return Model(
            original_type=cls,

            # Field definitions
            constructor=cls,
            fields=[
                Field(
                    name="red",
                    type=int,
                    description="Red level",
                    serialized_name="R",     # Defaults to name
                    argument_name="reddie",  # Defaults to name
                    property_name="red",     # Defaults to name
                ),
                Field(
                    name="green",
                    type=int,
                    description="Green level",
                    serialized_name="G",
                    argument_name="greenie",
                    property_name="green",
                ),
                Field(
                    name="blue",
                    type=int,
                    description="Blue level",
                    serialized_name="B",
                    argument_name="bluey",
                    property_name="blue",
                ),
            ],

            # String representation
            from_string=from_string=rgb_from_string,
            to_string=to_string=string_to_rgb,
            regexp=r"^#[0-9a-fA-F]{6}$",
            string_description="A RGB color in hex, such as #ff0000",
        )
```

!!!note
    * `property_name=None` on any field prevents serialization. You can do that if you only care about reading human-written configuration.
    * `argument_name=None` on any field prevents deserialization

```python
deserialize(RGB, {"R": 30, "G": 100, "B": 200})
# RGB(red=30, green=100, blue=200)

deserialize(RGB, "#ff0000")
# RGB(red=255, green=0, blue=0)

# When to_string is defined, string representation is preferred
serialize(RGB, RGB(reddie=1, greenie=2, bluey=3))
# "#010203"

schema(RGB).compile(root=False)
# {
#   "type": "object",
#   "pattern": "^#[0-9a-fA-F]{6}$",
#   "properties": {
#     "R": {"type": "integer", "description": "Red level"},
#     "G": {"type": "integer", "description": "Green level"},
#     "B": {"type": "integer", "description": "Blue level"}
#   },
#   "required": ["R", "G", "B"],
#   "description": "A RGB color in hex, such as #ff0000"
# }
```

## serieux_to_string

The `serieux_to_string` method defines how to convert an object to its string representation.

```python
@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @classmethod
    def serieux_to_string(cls, obj):
        return f"#{obj.red:02x}{obj.green:02x}{obj.blue:02x}"
```

Usage:

```python
serialize(RGB, RGB(red=255, green=0, blue=255))
# "#ff00ff"
```

## serieux_from_string

The `serieux_from_string` method defines how to transform a string back to an object.

```python
@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @classmethod
    def serieux_from_string(cls, s):
        hex_str = s.lstrip("#")
        red = int(hex_str[0:2], 16)
        green = int(hex_str[2:4], 16)
        blue = int(hex_str[4:6], 16)
        return cls(red=red, green=green, blue=blue)
```

Usage:

```python
deserialize(RGB, "#ff00ff")  # RGB(red=255, green=0, blue=255)
```

## serieux_deserialize

The `serieux_deserialize` method provides full control over how data is deserialized into an object. It may receive any JSON-compatible data structure and can fall back to default behavior using `call_next`.

```python
@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @classmethod
    def serieux_deserialize(cls, obj, ctx, call_next):
        if isinstance(obj, str):
            # Handle hex string format
            hex_str = obj.lstrip("#")
            red = int(hex_str[0:2], 16)
            green = int(hex_str[2:4], 16)
            blue = int(hex_str[4:6], 16)
            return cls(red=red, green=green, blue=blue)
        else:
            # Fall back to default deserialization for dict/object format
            return call_next(cls, obj, ctx)
```

Usage:

```python
deserialize(RGB, "#ff00ff")
# RGB(red=255, green=0, blue=255)

deserialize(RGB, {"red": 255, "green": 100, "blue": 100})
# RGB(red=255, green=100, blue=100)
```

## serieux_serialize

The `serieux_serialize` method provides full control over how an object is serialized. It can apply conditions and fall back to default behavior.

```python
@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        if 0 <= obj.red <= 255:
            return f"#{obj.red:02x}{obj.green:02x}{obj.blue:02x}"
        else:
            return call_next(cls, obj, ctx)
```

Usage:

```python
serialize(RGB, RGB(red=255, green=0, blue=255))
# "#ff00ff"

serialize(RGB, RGB(red=1000, green=0, blue=0))
# {"red": 1000, "green": 0, "blue": 0}
```

## serieux_schema

The `serieux_schema` method returns a JSON schema that describes the valid representations of the object.

```python
@dataclass
class RGB:
    red: int
    green: int
    blue: int

    @classmethod
    def serieux_schema(cls, ctx, call_next):
        return {
            "oneOf": [
                {"type": "string", "pattern": r"^#[0-9a-fA-F]{6}$"},
                call_next(cls, ctx),
            ]
        }
```

This generates a schema that accepts either a hex color string or the default object representation:

```json
{
  "oneOf": [
    {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
    {
      "type": "object",
      "properties": {
        "red": {"type": "integer"},
        "green": {"type": "integer"},
        "blue": {"type": "integer"}
      },
      "required": ["red", "green", "blue"],
      "additionalProperties": false
    }
  ]
}
```

