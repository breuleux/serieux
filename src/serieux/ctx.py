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
    def text(self):  # pragma: no cover
        return self.code[self.start : self.end]


class Located(Context):
    location: Location = None


@dataclass
class Patch:
    data: Callable | Any
    ctx: Context = None
    description: str | None = None

    def __post_init__(self):
        if self.description is None:
            self.description = f"Set to: {self.data!r}"

    def compute(self):
        if callable(self.data):  # pragma: no cover
            return self.data()
        else:
            return self.data

    def __str__(self):  # pragma: no cover
        return f"Patch({self.description!r})"


class Patcher(Context):
    patches: dict[int, tuple[Context, Any]] = field(default_factory=dict)

    def declare_patch(self, patch):
        if not isinstance(patch, Patch):
            patch = Patch(patch, ctx=self)
        elif not patch.ctx:  # pragma: no cover
            patch = replace(patch, ctx=self)
        start = patch.ctx.location.start if isinstance(patch.ctx, Located) else None
        self.patches[start] = patch

    def apply_patches(self):
        codes = {}
        patches = defaultdict(list)
        for patch in self.patches.values():
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
