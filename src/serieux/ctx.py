import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from ovld.medley import ChainAll, KeepLast, Medley

logger = logging.getLogger(__name__)


class Context(Medley, default_combiner=KeepLast):
    follow = ChainAll()


class EmptyContext(Context):
    pass


class AccessPath(Context):
    full_path: tuple = ()

    @property
    def access_path(self):
        return tuple(k for _, _, k in self.full_path)

    def follow(self, objt, obj, field):
        return replace(self, full_path=(*self.full_path, (objt, obj, field)))


@dataclass
class Location:
    source: Path
    code: str
    start: int
    end: int
    linecols: tuple

    @property
    def text(self):
        return self.code[self.start : self.end]


class Located(Context):
    location: Location = None


@dataclass
class Patch:
    data: Callable | Any
    ctx: Context = None
    description: str | None = None

    def compute(self):
        if callable(self.data):
            return self.data()
        else:
            return self.data

    def __str__(self):
        descr = self.description or self.data
        return f"Patch({descr!r})"


class Patcher(Context):
    patches: list[tuple[Context, Any]] = field(default_factory=list)

    def declare_patch(self, patch):
        if not isinstance(patch, Patch):
            patch = Patch(patch, ctx=self)
        elif not patch.ctx:
            patch = replace(patch, ctx=self)
        self.patches.append(patch)

    def apply_patches(self):
        codes = {}
        patches = defaultdict(list)
        for patch in self.patches:
            match patch.ctx:
                case Located(location=loc):
                    codes[loc.source] = loc.code
                    patches[loc.source].append((loc.start, loc.end, json.dumps(patch.compute())))
                case _:  # pragma: no cover
                    logger.warning(
                        f"Cannot apply patch at a context without a location: `{patch}`"
                    )

        for file, blocks in patches.items():
            code = codes[file].strip("\0")
            for start, end, content in sorted(blocks, reverse=True):
                code = code[:start] + content + code[end:]
            file.write_text(code)


empty = EmptyContext()
