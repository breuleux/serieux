
# Merging multiple configs

Serieux can gather information from multiple dicts, configuration files and others and merge everything into a single object. This is very useful for overriding values.

```python
from serieux import deserialize, Sources

# Assemble partial information
deserialize(Point, Sources({"x": 1}, {"y": 2}))
# => Point(1, 2)

# Override some fields
deserialize(Point, Sources({"x": 1, "y": 2}, {"x": 999}))
# => Point(999, 2)

# Merge configuration from two files
deserialize(Config, Sources(Path("cfg.yaml"), Path("overrides.yaml")))

# You can even do something like this
deserialize(Point, {"x": Sources(1, 999), "y": 2})
# => Point(999, 2)
```
