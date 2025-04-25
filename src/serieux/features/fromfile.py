import hashlib
import json
import tomllib
import uuid
from pathlib import Path
from typing import Any

import yaml
from ovld import call_next, dependent_check, ovld, recurse
from ovld.dependent import HasKey

from ..ctx import Context, Located, Location
from ..exc import ValidationError
from ..utils import PRIO_HIGHER, PRIO_LAST, clsstring
from .partial import PartialBuilding, Sources


@dependent_check
def FileSuffix(value: Path, *suffixes):
    return value.exists() and value.suffix in suffixes


@ovld
def parse(path: FileSuffix[".toml"]):  # type: ignore
    return tomllib.loads(path.read_text())


@ovld
def parse(path: FileSuffix[".json"]):  # type: ignore
    return json.loads(path.read_text())


@ovld
def parse(path: FileSuffix[".yaml", ".yml"]):  # type: ignore
    return yaml.compose(path.read_text()) or {}


@ovld
def parse(path: Path):
    raise ValidationError(f"Could not read data from file '{path}'")


class WorkingDirectory(Context):
    directory: Path = None
    origin: Path = None

    def __post_init__(self):
        if self.directory is None:
            self.directory = self.origin.parent

    def make_path_for(self, *, name=None, suffix=None, entropy=None):
        if name is None and entropy is not None:
            name = hashlib.md5(
                str(entropy).encode() if isinstance(entropy, str) else entropy
            ).hexdigest()
        if name is None:
            name = str(uuid.uuid4())
        pth = self.directory / name
        if suffix is not None:
            pth = pth.with_suffix(suffix)
        return pth

    def save_to_file(
        self, data: str | bytes = None, suffix=None, *, name=None, callback=None, entropy=None
    ):
        dest = self.make_path_for(entropy=entropy or data, suffix=suffix, name=name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if callback:
            callback(dest)
        else:
            if isinstance(data, str):
                mode = "w"
                encoding = "utf-8"
            else:
                mode = "wb"
                encoding = None
            with open(dest, mode=mode, encoding=encoding) as f:
                f.write(data)
        return str(dest.relative_to(self.directory))


def yaml_source_extract(node, ctx):
    return ctx + Located(
        location=Location(
            source=getattr(ctx, "origin", None),
            code=node.start_mark.buffer,
            start=node.start_mark.index,
            end=node.end_mark.index,
            linecols=(
                (node.start_mark.line, node.start_mark.column),
                (node.end_mark.line, node.end_mark.column),
            ),
        )
    )


@dependent_check
def ScalarNode(value: yaml.ScalarNode, tag_suffix):
    return value.tag.endswith(tag_suffix)


class FromFile(PartialBuilding):
    def deserialize(self, t: Any, obj: Path, ctx: Context):
        if isinstance(ctx, WorkingDirectory):
            obj = ctx.directory / obj.expanduser()
        data = parse(obj)
        ctx = ctx + WorkingDirectory(origin=obj, directory=obj.parent)
        return recurse(t, data, ctx)

    @ovld(priority=PRIO_HIGHER)
    def deserialize(self, t: Any, obj: yaml.MappingNode, ctx: Context):
        return recurse(t, {k.value: v for k, v in obj.value}, yaml_source_extract(obj, ctx))

    @ovld(priority=PRIO_HIGHER)
    def deserialize(self, t: Any, obj: yaml.SequenceNode, ctx: Context):
        return recurse(t, obj.value, yaml_source_extract(obj, ctx))

    @ovld(priority=PRIO_HIGHER)
    def deserialize(self, t: Any, obj: ScalarNode[":str"], ctx: Context):  # type: ignore
        return recurse(t, obj.value, yaml_source_extract(obj, ctx))

    @ovld(priority=PRIO_HIGHER)
    def deserialize(self, t: Any, obj: ScalarNode[":int"], ctx: Context):  # type: ignore
        return recurse(t, int(obj.value), yaml_source_extract(obj, ctx))

    @ovld(priority=PRIO_HIGHER)
    def deserialize(self, t: Any, obj: ScalarNode[":float"], ctx: Context):  # type: ignore
        return recurse(t, float(obj.value), yaml_source_extract(obj, ctx))

    @ovld(priority=PRIO_HIGHER)
    def deserialize(self, t: Any, obj: ScalarNode[":bool"], ctx: Context):  # type: ignore
        value = obj.value.lower() in ("yes", "on", "true")
        return recurse(t, value, yaml_source_extract(obj, ctx))

    @ovld(priority=PRIO_HIGHER)
    def deserialize(self, t: Any, obj: ScalarNode[":null"], ctx: Context):  # type: ignore
        return recurse(t, None, yaml_source_extract(obj, ctx))

    @ovld(priority=PRIO_HIGHER)
    def deserialize(self, t: Any, obj: ScalarNode[":timestamp"], ctx: Context):  # type: ignore
        return recurse(t, obj.value, yaml_source_extract(obj, ctx))

    @ovld(priority=PRIO_HIGHER)
    def deserialize(self, t: Any, obj: yaml.ScalarNode, ctx: Context):  # pragma: no cover
        raise ValidationError(f"Cannot deserialize YAML node of type `{obj.tag}`")


class FromFileExtra(FromFile):
    @ovld(priority=1)
    def deserialize(self, t: type[object], obj: HasKey["$include"], ctx: Context):
        obj = dict(obj)
        incl = recurse(str, obj.pop("$include"), ctx)
        return recurse(t, Sources(Path(incl), obj), ctx)

    @ovld(priority=PRIO_LAST)
    def deserialize(self, t: type[object], obj: str, ctx: WorkingDirectory):
        if "." not in obj or obj.rsplit(".", 1)[1].isnumeric():
            return call_next(t, obj, ctx)

        path = ctx.directory / obj
        if path.exists():
            return recurse(t, path, ctx)
        else:
            raise ValidationError(
                f"Tried to read '{obj}' as a configuration file (at path '{path}')"
                f" to deserialize into object of type {clsstring(t)},"
                " but there was no such file."
            )


# Add as a default feature in serieux.Serieux
# But we do not have FromFileExtra by default
__default_features__ = FromFile
