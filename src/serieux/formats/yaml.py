from pathlib import Path

import yaml
from ovld import dependent_check, ovld, recurse

from ..ctx import Location
from .abc import FileFormat


def yaml_source_extract(node, origin):
    return Location(
        source=origin,
        code=node.start_mark.buffer,
        start=node.start_mark.index,
        end=node.end_mark.index,
        linecols=(
            (node.start_mark.line, node.start_mark.column),
            (node.end_mark.line, node.end_mark.column),
        ),
    )


@dependent_check
def ScalarNode(value: yaml.ScalarNode, tag_suffix):
    return value.tag.endswith(tag_suffix)


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
    return yaml_source_extract(obj, origin)


@ovld
def locate(obj: yaml.ScalarNode, origin: Path, access_path: tuple | list):
    return yaml_source_extract(obj, origin)


class YAML(FileFormat):
    def locate(self, f: Path, access_path: tuple[str]):
        return locate(yaml.compose(f.read_text()), f, access_path)

    def load(self, f: Path):
        with open(f, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def dump(self, f: Path, data):
        with open(f, "w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
