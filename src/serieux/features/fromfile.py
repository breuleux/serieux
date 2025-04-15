import hashlib
import json
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml
from ovld import call_next, dependent_check, ovld, recurse
from ovld.dependent import HasKey

from ..ctx import Context
from ..exc import ValidationError
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
    return yaml.compose(path.read_text())


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


class FromFile(PartialBuilding):
    def deserialize(self, t: type[object], obj: Path, ctx: Context):
        if isinstance(ctx, WorkingDirectory):
            obj = ctx.directory / obj
        data = parse(obj)
        ctx = ctx + WorkingDirectory(origin=obj, directory=obj.parent)
        return recurse(t, data, ctx)

    def deserialize(self, t: type[object], obj: yaml.MappingNode, ctx: Context):
        return recurse(t, {k.value: v for k, v in obj.value}, ctx + YamlSourceInfo.extract(obj))

    def deserialize(self, t: type[object], obj: yaml.SequenceNode, ctx: Context):
        return recurse(t, obj.value, ctx + YamlSourceInfo.extract(obj))

    def deserialize(self, t: type[object], obj: ScalarNode[":str"], ctx: Context):  # type: ignore
        return recurse(t, obj.value, ctx + YamlSourceInfo.extract(obj))

    def deserialize(self, t: type[object], obj: ScalarNode[":int"], ctx: Context):  # type: ignore
        return recurse(t, int(obj.value), ctx + YamlSourceInfo.extract(obj))

    def deserialize(self, t: type[object], obj: ScalarNode[":float"], ctx: Context):  # type: ignore
        return recurse(t, float(obj.value), ctx + YamlSourceInfo.extract(obj))


class FromFileExtra(FromFile):
    @ovld(priority=1)
    def deserialize(self, t: type[object], obj: HasKey["$include"], ctx: Context):
        obj = dict(obj)
        incl = recurse(str, obj.pop("$include"), ctx)
        return recurse(t, Sources(Path(incl), obj), ctx)

    @ovld(priority=-50)
    def deserialize(self, t: type[object], obj: str, ctx: WorkingDirectory):
        path = ctx.directory / obj
        if path.exists():
            return recurse(t, path, ctx)
        else:
            return call_next(t, obj, ctx)


# Add as a default feature in serieux.Serieux
# But we do not have FromFileExtra by default
__default_features__ = FromFile
