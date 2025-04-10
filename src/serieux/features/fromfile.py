import hashlib
import json
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml
from ovld import dependent_check, ovld, recurse
from ovld.dependent import HasKey

from ..ctx import Context
from .partial import PartialBuilding, Sources


@dependent_check
def FileSuffix(value: Path, *suffixes):
    return value.exists() and value.suffix in suffixes


@ovld
def parse(path: FileSuffix[".toml"]):
    return tomllib.loads(path.read_text())


@ovld
def parse(path: FileSuffix[".json"]):
    return json.loads(path.read_text())


@ovld
def parse(path: FileSuffix[".yaml", ".yml"]):
    return yaml.safe_load(path.read_text())


@ovld
def parse_with_source(path: FileSuffix[".yaml", ".yml"]):
    return yaml.compose(path.read_text())


class WorkingDirectory(Context):
    directory: Path = None
    origin: Path = None

    def __post_init__(self):
        if self.directory is None:
            self.directory = self.origin.parent

    def make_path_for(self, *, name=None, suffix=None, data=None):
        if name is None and data is not None:
            name = hashlib.md5(str(data).encode() if isinstance(data, str) else data).hexdigest()
        if name is None:
            name = str(uuid.uuid4())
        pth = self.directory / name
        if suffix is not None:
            pth = pth.with_suffix(suffix)
        return pth

    def save_to_file(self, data: str | bytes, suffix=None, *, name=None, method=None):
        dest = self.make_path_for(data=data, suffix=suffix, name=name)
        if isinstance(data, str):
            mode = "w"
            encoding = "utf-8"
        else:
            mode = "wb"
            encoding = None
        dest.parent.mkdir(parents=True, exist_ok=True)
        if method:
            method(dest)
        else:
            with open(dest, mode=mode, encoding=encoding) as f:
                f.write(data)
        return str(dest.relative_to(self.directory))


@dataclass
class Location:
    source: str
    start: int
    end: int
    linecols: tuple


class YamlSourceInfo(Context):
    location: Location

    @classmethod
    def extract(cls, node):
        return cls(
            location=Location(
                source=node.start_mark.buffer,
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


class FromFileFeature(PartialBuilding):
    @ovld(priority=1)
    def deserialize(self, t: type[object], obj: HasKey["$include"], ctx: Context):
        obj = dict(obj)
        incl = recurse(str, obj.pop("$include"), ctx)
        return recurse(t, Sources(Path(incl), obj), ctx)

    def deserialize(self, t: type[object], obj: Path, ctx: Context):
        if isinstance(ctx, WorkingDirectory):
            obj = ctx.directory / obj
        data = parse(obj)
        ctx = ctx + WorkingDirectory(origin=obj, directory=obj.parent)
        try:
            return recurse(t, data, ctx)
        except Exception:
            pass
        data = parse_with_source(obj)
        return recurse(t, data, ctx)

    def deserialize(self, t: type[object], obj: yaml.MappingNode, ctx: Context):
        return recurse(t, {k.value: v for k, v in obj.value}, ctx + YamlSourceInfo.extract(obj))

    def deserialize(self, t: type[object], obj: yaml.SequenceNode, ctx: Context):
        return recurse(t, obj.value, ctx + YamlSourceInfo.extract(obj))

    def deserialize(self, t: type[object], obj: ScalarNode[":str"], ctx: Context):
        return recurse(t, obj.value, ctx + YamlSourceInfo.extract(obj))

    def deserialize(self, t: type[object], obj: ScalarNode[":int"], ctx: Context):
        return recurse(t, int(obj.value), ctx + YamlSourceInfo.extract(obj))

    def deserialize(self, t: type[object], obj: ScalarNode[":float"], ctx: Context):
        return recurse(t, float(obj.value), ctx + YamlSourceInfo.extract(obj))


# Currently not a default feature
__default_features__ = None
