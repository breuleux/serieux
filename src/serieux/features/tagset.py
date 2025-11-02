import importlib
import importlib.metadata
from collections import deque
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Annotated, Any, Callable, Iterable, TypeAlias, Union

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import BaseInstruction, Instruction, T, annotate, pushdown, strip
from ..model import constructed_type
from ..schema import AnnotatedSchema
from ..tell import KeyValueTell, tells

tag_field = "$class"
value_field = "$value"


class TagSet(BaseInstruction):  # pragma: no cover
    def get_type(self, tag: str | None, ctx: Context = None) -> type:
        raise NotImplementedError()

    def get_tag(self, t: type, ctx: Context = None) -> str | None:
        raise NotImplementedError()

    def iterate(self, base: type, ctx: Context = None) -> Iterable[tuple[str | None, type]]:
        raise NotImplementedError()

    def closed(self, base):
        return True


@dataclass(frozen=True, eq=False)
class TagDict(TagSet):
    possibilities: dict = field(default_factory=dict)

    def register(self, tag_or_cls=None, cls=None):
        if isinstance(tag_or_cls, str):
            tag = tag_or_cls

            def decorator(cls):
                self.possibilities[tag] = cls
                return cls

            return decorator if cls is None else decorator(cls)

        else:
            assert cls is None
            cls = tag_or_cls
            tag = cls.__name__.lower()
            self.possibilities[tag] = cls
            return cls

    def get_type(self, tag: str | None, ctx: Context = None) -> type:
        if tag is None:
            return self.get_type("default", ctx)
        try:
            return self.possibilities[tag]
        except KeyError:
            raise ValidationError(f"Tag '{tag}' is not registered", ctx=ctx)

    def get_tag(self, t: type, ctx: Context = None) -> str | None:
        for tag, cls in self.possibilities.items():
            if cls is t:
                return None if tag == "default" else tag
        raise ValidationError(f"No tag is registered for type '{t}'", ctx=ctx)

    def iterate(self, base: type, ctx: Context = None) -> Iterable[tuple[str | None, type]]:
        yield from self.possibilities.items()


@dataclass(frozen=True)
class Tag(TagSet):
    tag: str
    cls: type

    def get_type(self, tag: str | None, ctx: Context = None) -> type:
        if tag is None:
            raise ValidationError(f"Tag '{self.tag}' is required", ctx=ctx)
        if tag == self.tag:
            return self.cls
        raise ValidationError(f"Tag '{tag}' does not match expected tag '{self.tag}'", ctx=ctx)

    def get_tag(self, t: type, ctx: Context = None) -> str | None:
        if t is self.cls:
            return self.tag
        raise ValidationError(f"Type '{t}' does not match expected class '{self.cls}'", ctx=ctx)

    def iterate(self, base: type, ctx: Context = None) -> Iterable[tuple[str | None, type]]:
        if isinstance(base, type):
            assert issubclass(self.cls, base)
        yield (self.tag, self.cls)


@dataclass(frozen=True)
class FromEntryPoint(TagSet):
    entry_point: str
    default: type = None
    wrap: Callable = None

    @cached_property
    def elements(self):
        def _wrap(t):
            match self.wrap:
                case None:
                    return t
                case type() | Instruction():  # pragma: no cover
                    return self.wrap[t]
                case _:
                    return self.wrap(t)

        eps = importlib.metadata.entry_points(group=self.entry_point)
        return {ep.name: cls for ep in eps if (cls := _wrap(ep.load())) is not None}

    def get_type(self, tag: str | None, ctx: Context) -> type:
        eps = self.elements
        if tag is None:
            if self.default is not None:
                return self.default
            raise ValidationError("No tag provided for entry point lookup", ctx=ctx)
        try:
            return eps[tag]
        except KeyError:
            raise ValidationError(
                f"Tag '{tag}' is not registered in entry point group '{self.entry_point}'", ctx=ctx
            )

    def get_tag(self, t: type, ctx: Context) -> str | None:
        if t is self.default:
            return None
        for name, cls in self.elements.items():
            if cls is t:
                return name
        raise ValidationError(
            f"No entry point tag is registered for type '{t}' in group '{self.entry_point}'",
            ctx=ctx,
        )

    def iterate(self, base: type, ctx: Context = None) -> Iterable[tuple[str | None, type]]:
        for name, cls in self.elements.items():
            if base is Any or issubclass(cls, base):
                yield (name, cls)
        if self.default is not None and (base is Any or issubclass(self.default, base)):
            yield (None, self.default)


@dataclass(frozen=True)
class _ReferencedClass(TagSet):
    default: type = None
    default_module: str = None

    def get_type(self, tag: str | None, ctx: Context) -> type:
        if tag is None:
            if self.default is not None:
                return self.default
            else:
                raise ValidationError("No default class is defined when there is no explicit tag")

        if (ncolon := tag.count(":")) == 0:
            mod_name = self.default_module
            if mod_name is None:
                raise ValidationError(
                    "The reference does not specify a module and no default module is defined",
                    ctx=ctx,
                )
            symbol = tag
        elif ncolon == 1:
            mod_name, symbol = tag.split(":")
        else:
            raise ValidationError(f"Bad format for class reference: '{tag}'", ctx=ctx)
        try:
            mod = importlib.import_module(mod_name)
            return getattr(mod, symbol)
        except (ModuleNotFoundError, AttributeError) as exc:
            raise ValidationError(exc=exc, ctx=ctx)

    def get_tag(self, t: type, ctx: Context) -> str | None:
        qn = t.__qualname__
        if "." in qn:
            raise ValidationError("Only top-level symbols can be serialized", ctx=ctx)
        mod = t.__module__
        return f"{mod}:{qn}"

    def iterate(self, base: type, ctx: Context = None) -> Iterable[tuple[str | None, type]]:
        if base is Any or base is object:
            return
        queue = deque([base])
        while queue:
            sc = queue.popleft()
            sc_mod = sc.__module__
            sc_name = sc.__name__
            if sc is self.default:
                tag = None
            elif sc_mod is self.default_module:
                tag = sc_name
            else:
                tag = f"{sc_mod}:{sc_name}"
            yield tag, sc
            queue.extend(sc.__subclasses__())

    def closed(self, base):
        return base is not Any and base is not object

    def __call__(self, *args, **kwargs):
        return type(self)(*args, **kwargs)


ReferencedClass = _ReferencedClass()


class MultiTagSet(TagSet):
    def __init__(self, *tagsets):
        assert tagsets
        self.tagsets = tagsets

    def get_type(self, tag, ctx):
        for ts in self.tagsets:
            try:
                return ts.get_type(tag, ctx)
            except ValidationError:
                pass
        raise ValidationError("No tagset could resolve the tag", ctx=ctx)

    def get_tag(self, t, ctx):
        for ts in self.tagsets:
            try:
                return ts.get_tag(t, ctx)
            except ValidationError:
                pass
        raise ValidationError(f"No tagset could resolve for type {t}", ctx=ctx)

    def iterate(self, base, ctx=None):
        seen = set()
        for ts in self.tagsets:
            for tag, sc in ts.iterate(base, ctx):
                if tag not in seen:
                    seen.add(tag)
                    yield tag, sc

    def closed(self, base):
        return all(ts.closed(base) for ts in self.tagsets)


def decompose(annt):
    base = pushdown(annt)
    match list(TagSet.extract_all(annt)):
        case (ts,):
            pass
        case many:
            ts = MultiTagSet(*many)
    return base, ts


class TagSetFeature(Medley):
    @ovld(priority=10)
    def serialize(self, t: type[Any @ TagSet], obj: object, ctx: Context, /):
        base, ts = decompose(t)
        if base is not Any and not isinstance(obj, base):
            raise ValidationError(f"'{obj}' is not a subclass of '{base}'", ctx=ctx)
        objt = type(obj)
        tag = ts.get_tag(objt, ctx)
        rval = call_next(objt, obj, ctx)
        if not isinstance(rval, dict):
            rval = {value_field: rval}
        if tag is not None:
            rval[tag_field] = tag
        return rval

    def deserialize(self, t: type[Any @ TagSet], obj: dict, ctx: Context, /):
        base, ts = decompose(t)
        data = dict(obj)
        tag = data.pop(tag_field, None)
        data = data.pop(value_field, data)
        if tag is not None:
            tag = recurse(str, tag, ctx)
        declared = ts.get_type(tag, ctx)
        if base is not Any and base is not object and isinstance(base, type):
            actual_class = constructed_type(declared)
            if not issubclass(actual_class, base):
                raise ValidationError(f"'{actual_class}' is not a subclass of '{base}'", ctx=ctx)
        return recurse(strip(annotate(declared, t), TagSet), data, ctx)

    def schema(self, t: type[Any @ TagSet], ctx: Context):
        base, ts = decompose(t)
        subschemas = []
        for tag, sc in ts.iterate(base, ctx):
            if base is not Any and not issubclass(sc, base):  # pragma: no cover
                continue
            subsch = recurse(strip(annotate(sc, t), TagSet))
            if tag is not None:
                subsch = AnnotatedSchema(
                    parent=subsch,
                    properties={
                        tag_field: {
                            "description": "Reference to the class to instantiate",
                            "const": tag,
                        }
                    },
                    required=[tag_field],
                )
            subschemas.append(subsch)
        if not ts.closed(base):
            subschemas.append({"type": "object", "additionalProperties": True})
        if len(subschemas) == 1:
            return subschemas[0]
        else:
            return {"oneOf": subschemas}


@tells.register(priority=1)
def tells(expected: type[Any @ TagSet], given: type[dict]):
    base, ts = decompose(expected)
    return {KeyValueTell(tag_field, tag) for tag, _ in ts.iterate(base)}


if TYPE_CHECKING:
    TaggedSubclass: TypeAlias = Annotated[T, None]
    Tagged: TypeAlias = Annotated
    TaggedUnion = Union

else:

    class TaggedSubclass:
        def __class_getitem__(cls, item):
            return Annotated[item, ReferencedClass(default=item, default_module=item.__module__)]

    class Tagged(type):
        def __class_getitem__(cls, arg):
            match arg:
                case (t, name):
                    return Annotated[t, Tag(name, t)]
                case t:
                    st = strip(t)
                    tag = getattr(st, "serieux_tag", None) or st.__name__.lower()
                    return Annotated[t, Tag(tag, t)]

    class TaggedUnion(type):
        def __class_getitem__(cls, args):
            if isinstance(args, dict):
                return Union[tuple(Tagged[v, k] for k, v in args.items())]
            elif not isinstance(args, (list, tuple)):
                return Tagged[args]
            return Union[tuple(Tagged[arg] for arg in args)]
