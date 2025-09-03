import json
from pathlib import Path

from ovld import ovld, recurse

from ..ctx import Location
from ..utils import import_any
from .abc import FileFormat

yaml = import_any(
    feature="YAML loading and dumping",
    candidates={
        "pyyaml:yaml": lambda m: m,
    },
)

Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
Dumper = getattr(yaml, "CSafeDumper", yaml.SafeDumper)


def yaml_source_extract(node, origin):
    return Location(
        source=origin,
        start=node.start_mark.index,
        end=node.end_mark.index,
        linecols=(
            (node.start_mark.line, node.start_mark.column),
            (node.end_mark.line, node.end_mark.column),
        ),
    )


@ovld
def locate(obj: yaml.MappingNode, origin: Path, access_path: tuple | list):
    if access_path:
        nxt, *rest = access_path
        for k, v in obj.value:
            if k.value == nxt:
                return recurse(v, origin, rest)
    return yaml_source_extract(obj, origin)


@ovld
def locate(obj: yaml.SequenceNode, origin: Path, access_path: tuple | list):
    if access_path:
        nxt, *rest = access_path
        for i, v in enumerate(obj.value):
            if i == nxt:
                return recurse(v, origin, rest)
    return yaml_source_extract(obj, origin)  # pragma: no cover


@ovld
def locate(obj: yaml.ScalarNode, origin: Path, access_path: tuple | list):
    return yaml_source_extract(obj, origin)


class YAML(FileFormat):
    def locate(self, f: Path, access_path: tuple[str]):
        return locate(yaml.compose(f.read_text(), Loader), f, access_path)

    def patch(self, source, patches):
        for start, end, content in sorted(patches, reverse=True):
            source = source[:start] + json.dumps(content) + source[end:]
        return source

    def load(self, f: Path):
        with open(f, "r") as of:
            return yaml.load(of, Loader)

    def dump(self, f: Path, data):
        with open(f, "w") as of:
            yaml.dump(data, of, Dumper=Dumper, allow_unicode=True, sort_keys=False)
