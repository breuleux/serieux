import importlib
import importlib.metadata
from collections import deque
from dataclasses import dataclass, field
from typing import Annotated, Any, Iterable, Union

from ovld import Medley, call_next, ovld, recurse

from ..ctx import Context
from ..exc import ValidationError
from ..instructions import BaseInstruction, annotate, pushdown, strip
from ..schema import AnnotatedSchema
from ..tell import KeyValueTell, TypeTell, tells


@dataclass(frozen=True)
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
                return tag
        raise ValidationError(f"No tag is registered for type '{t}'", ctx=ctx)

    def iterate(self, base: type, ctx: Context = None) -> Iterable[tuple[str | None, type]]:
        yield from self.possibilities.items()


@dataclass(frozen=True)
class LoneTag(TagSet):
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
        assert issubclass(self.cls, base)
        yield (self.tag, self.cls)


class Tagged(type):
    def __class_getitem__(cls, arg):
        match arg:
            case (t, name):
                return Annotated[t, LoneTag(name, t)]
            case t:
                t = strip(t)
                tag = getattr(t, "__tag__", None) or t.__name__.lower()
                return Annotated[t, LoneTag(tag, t)]


class TaggedUnion(type):
    def __class_getitem__(cls, args):
        if isinstance(args, dict):
            return Union[tuple(Tagged[v, k] for k, v in args.items())]
        elif not isinstance(args, (list, tuple)):
            return Tagged[args]
        return Union[tuple(Tagged[arg] for arg in args)]


@dataclass(frozen=True)
class FromEntryPoint(TagSet):
    entry_point: str

    def _load_entry_points(self):
        eps = importlib.metadata.entry_points()
        group_eps = eps.select(group=self.entry_point)
        return {ep.name: ep.load() for ep in group_eps}

    def get_type(self, tag: str | None, ctx: Context) -> type:
        eps = self._load_entry_points()
        if tag is None:
            raise ValidationError("No tag provided for entry point lookup", ctx=ctx)
        try:
            return eps[tag]
        except KeyError:
            raise ValidationError(
                f"Tag '{tag}' is not registered in entry point group '{self.entry_point}'", ctx=ctx
            )

    def get_tag(self, t: type, ctx: Context) -> str | None:
        eps = self._load_entry_points()
        for name, cls in eps.items():
            if cls is t:
                return name
        raise ValidationError(
            f"No entry point tag is registered for type '{t}' in group '{self.entry_point}'",
            ctx=ctx,
        )

    def iterate(self, base: type, ctx: Context) -> Iterable[tuple[str | None, type]]:
        eps = self._load_entry_points()
        for name, cls in eps.items():
            if issubclass(cls, base):
                yield (name, cls)


@dataclass(frozen=True)
class ReferencedClass(TagSet):
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

    def iterate(self, base: type, ctx: Context) -> Iterable[tuple[str | None, type]]:
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
                tag = f"{sc_name}:{sc_mod}"
            yield tag, sc
            queue.extend(sc.__subclasses__())

    def closed(self, base):
        return base is not Any and base is not object

    def __call__(self, *args, **kwargs):
        return type(self)(*args, **kwargs)


Referenced = ReferencedClass()


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

    def iterate(self, base, ctx):
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
            rval = {"return": rval}
        rval["class"] = tag
        return rval

    def deserialize(self, t: type[Any @ TagSet], obj: dict, ctx: Context, /):
        base, ts = decompose(t)
        obj = dict(obj)
        tag = obj.pop("class", None)
        obj = obj.pop("return", obj)
        if tag is not None:
            tag = recurse(str, tag, ctx)
        actual_class = ts.get_type(tag, ctx)
        if base is not Any and not issubclass(actual_class, base):
            raise ValidationError(f"'{actual_class}' is not a subclass of '{base}'", ctx=ctx)
        print(strip(annotate(actual_class, t), TagSet))
        return recurse(strip(annotate(actual_class, t), TagSet), obj, ctx)

    def schema(self, t: type[Any @ TagSet], ctx: Context):
        base, ts = decompose(t)
        subschemas = []
        for tag, sc in ts.iterate(base, ctx):
            if not issubclass(sc, base):
                continue
            subsch = recurse(strip(annotate(sc, t), TagSet))
            if tag is not None:
                subsch = AnnotatedSchema(
                    parent=subsch,
                    properties={
                        "class": {
                            "description": "Reference to the class to instantiate",
                            "const": tag,
                        }
                    },
                    required=["class"],
                )
            subschemas.append(subsch)
        if not ts.closed(base):
            subschemas.append({"type": "object", "additionalProperties": True})
        if len(subschemas) == 1:
            return subschemas[0]
        else:
            return {"oneOf": subschemas}


@tells.register(priority=1)
def tells(typ: type[Any @ TagSet]):
    base, ts = decompose(typ)
    kvt = [KeyValueTell("class", tag) for tag, _ in ts.iterate(base)]
    return {TypeTell(dict), *kvt}


class TaggedSubclass:
    def __class_getitem__(cls, item):
        return Annotated[item, Referenced(default=item, default_module=item.__module__)]


# Add as a default feature in serieux.Serieux
__default_features__ = TagSetFeature
