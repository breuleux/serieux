from functools import cache


class State:
    __combines__ = None

    def __add__(self, other):
        assert isinstance(other, State)
        classes = set()
        parts = {}
        for x in (self, other):
            if x.__combines__:
                classes.update(x.__combines__)
                parts.update(x.__parts__)
            else:
                t = type(x)
                classes.add(t)
                parts[t.__name__] = x
        if len(classes) == 1:
            return other
        cls = combine(frozenset(classes))
        return cls(parts)

    def __sub__(self, other):
        if not isinstance(other, type):
            other = type(other)
            assert not other.__combines__
        if self.__combines__:
            classes = self.__combines__ - {other}
            parts = {k: v for k, v in self.__parts__.items() if k != other.__name__}
            if len(classes) == 1:
                return list(parts.values())[0]
            cls = combine(frozenset(classes))
            return cls(parts)
        elif type(self) is other:
            return EmptyState()
        else:
            return self


class EmptyState(State):
    def __add__(self, other):
        return other

    def __sub__(self, other):
        return self


class Forwarder:
    def __init__(self, group, field):
        self.group = group
        self.field = field

    def __get__(self, obj, cls):
        return getattr(getattr(obj or cls, self.group), self.field)

    def __set__(self, obj, value):
        setattr(getattr(obj, self.group), self.field, value)


@cache
def combine(classes: frozenset):
    assert isinstance(classes, frozenset)
    assert len(classes) > 1

    dct = {c.__name__: c for c in classes}
    dct["__combines__"] = classes
    for c in classes:
        all_names = set(c.__annotations__) | set(dir(c))
        names = {x for x in all_names if not x.startswith("__")}
        fwds = {name: Forwarder(c.__name__, name) for name in names}
        dct.update(fwds)

    def init(self, objs):
        self.__parts__ = objs
        self.__dict__.update(objs)

    dct["__init__"] = init

    return type(
        "+".join(c.__name__ for c in classes),
        tuple(classes),
        dct,
    )


empty = EmptyState()
