
# Structured comments

The `Comment` and `CommentRec` type annotations let you specify a data type that you can "comment" data with: any data in the `$comment` field will have to match that type and will be stashed into the `_` attribute of the resulting object.

```python
from serieux import Comment

pt = deserialize(Comment[Point, str], {"x": 1, "y": 2, "$comment": "what a boring point"})
assert isinstance(pt, Point)  # But it is actually a CommentProxy instance
assert pt.x == 1
assert pt.y == 2
assert pt._ == "what a boring point"
```

`Comment` only applies to the type it annotates. `CommentRec`, by contrast, applies recursively, so you can comment anything within that tree.

```python
from serieux import CommentRec

pt = deserialize(CommentRec[Point, str], {"x": 1, "y": {"$value": 2, "$comment": "two"}})
assert pt.y == 2
assert pt.y._ == "two"
```

!!!note
    This feature works through the `CommentProxy` class, which proxies all attributes and method calls to the underlying object. It may not be 100% transparent, so commented objects may sometimes behave differently.
