import json
import tomllib
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
    origin: Path
    directory: Path


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
        return recurse(t, Sources(Path(obj.pop("$include")), obj), ctx)

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
