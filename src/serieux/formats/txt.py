from pathlib import Path

from ..ctx import Location
from .abc import FileFormat


class Text(FileFormat):
    def locate(self, f: Path, trail: tuple[str]):
        if trail == ():
            txt = f.read_text()
            lines = txt.splitlines(keepends=True)
            return Location(
                source=f,
                start=0,
                end=len(txt),
                linecols=((0, 0), (len(lines), len(lines[-1]))),
            )

    def patch(self, source, patches):
        for start, end, content in sorted(patches, reverse=True):
            source = source[:start] + content + source[end:]
        return source

    def loads(self, s: str):
        return s

    def dumps(self, data):
        return data
