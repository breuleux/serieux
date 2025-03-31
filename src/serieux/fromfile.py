import json
import tomllib
from pathlib import Path

import yaml
from ovld import Medley, dependent_check, ovld, recurse
from ovld.dependent import HasKey

from .ctx import Context
from .partial import PartialFeature, Sources


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


class WorkingDirectory(Context):
    directory: Path


class FromFileFeature(Medley):
    @ovld(priority=1)
    def deserialize(self, t: type[object], obj: HasKey["$include"], ctx: Context):
        obj = dict(obj)
        return recurse(t, Sources(Path(obj.pop("$include")), obj), ctx)

    def deserialize(self, t: type[object], obj: Path, ctx: Context):
        if isinstance(ctx, WorkingDirectory):
            obj = ctx.directory / obj
        data = parse(obj)
        return recurse(t, data, ctx + WorkingDirectory(obj.parent))


FromFileFeature += PartialFeature
