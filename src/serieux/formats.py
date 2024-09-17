from pathlib import Path

import yaml
from ovld import OvldMC, call_next, dependent_check, extend_super, ovld, recurse

from .proxy import Source, deprox, proxy, reprox


@dependent_check
def ScalarNode(value: yaml.ScalarNode, tag_suffix):
    return value.tag.endswith(tag_suffix)


@dependent_check
def FileSuffix(value: Path, *suffixes):
    return value.exists() and value.suffix in suffixes


class YamlParser:
    def __init__(self, origin, source=None):
        self.origin = origin
        self.source = Path(origin).read_text() if source is None else source

    @ovld
    def parse(self):
        return recurse(yaml.compose(self.source))

    @ovld(priority=1)
    def parse(self, node: yaml.Node):
        rval = call_next(node)
        src = Source(
            origin=self.origin,
            source=self.source,
            start=node.start_mark.index,
            end=node.end_mark.index,
            linecols=(
                (node.start_mark.line, node.start_mark.column),
                (node.end_mark.line, node.end_mark.column),
            ),
        )
        return proxy(rval, {Source: src})

    @ovld
    def parse(self, node: yaml.MappingNode):
        return {recurse(k): recurse(v) for k, v in node.value}

    @ovld
    def parse(self, node: yaml.SequenceNode):
        return [recurse(x) for x in node.value]

    @ovld
    def parse(self, node: ScalarNode[":str"]):  # type: ignore
        return node.value

    @ovld
    def parse(self, node: ScalarNode[":int"]):  # type: ignore
        return int(node.value)

    @ovld
    def parse(self, node: ScalarNode[":float"]):  # type: ignore
        return float(node.value)


class YamlMixin(metaclass=OvldMC):
    @extend_super
    def deserialize_partial(self, to: object, frm: FileSuffix[".yaml", ".yml"]):  # type: ignore
        return reprox(
            result=recurse(to, YamlParser(origin=deprox(frm)).parse()),
            original=frm,
        )
