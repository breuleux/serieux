import hashlib
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from typing import Any, Callable

from ovld.medley import ChainAll, KeepLast, Medley

from .formats.abc import FileFormat

logger = logging.getLogger(__name__)


class Context(Medley, default_combiner=KeepLast):
    follow = ChainAll()


class EmptyContext(Context):
    def __add__(self, other):
        return other

    def __radd__(self, other):  # pragma: no cover
        return other


class Trail(Context):
    full_trail: tuple = ()

    @property
    def trail(self):
        return tuple(k for _, _, k in self.full_trail)

    def follow(self, objt, obj, field):
        return replace(self, full_trail=(*self.full_trail, (objt, obj, field)))


@dataclass
class Location:
    source: Path
    start: int
    end: int
    linecols: tuple

    @cached_property
    def whole_text(self):
        return self.source.read_text()

    @property
    def text(self):  # pragma: no cover
        return self.whole_text[self.start : self.end]


class WorkingDirectory(Context):
    directory: Path = None

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


class Sourced(WorkingDirectory):
    origin: Path = None
    format: FileFormat = None
    source_trail: tuple = ()

    def __post_init__(self):
        if self.directory is None:
            self.directory = self.origin.parent

    def compute_location(self, trail=None):
        if isinstance(self, Trail):
            trail = self.trail
            pfx = len(self.source_trail)
            if trail[:pfx] != self.source_trail:  # pragma: no cover
                return None
            trail = trail[pfx:]
            return self.format.locate(self.origin, trail)
        return None  # pragma: no cover


def locate(ctx):
    if isinstance(ctx, Sourced):
        return ctx.compute_location()
    else:
        return None


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


class Patcher(Trail):
    patches: dict[int, tuple[Context, Any]] = field(default_factory=dict)

    def declare_patch(self, patch):
        if not isinstance(patch, Patch):
            patch = Patch(patch, ctx=self)
        elif not patch.ctx:  # pragma: no cover
            patch = replace(patch, ctx=self)
        if start := (loc := locate(patch.ctx)) and loc.start:
            self.patches[start] = patch

    def apply_patches(self, file_remap=None):
        codes = {}
        patches = defaultdict(list)
        for patch in self.patches.values():
            if loc := locate(patch.ctx):
                codes[loc.source] = loc.whole_text
                patches[loc.source].append((loc.start, loc.end, patch.compute()))
            else:  # pragma: no cover
                logger.warning(f"Cannot apply patch at a context without a location: `{patch}`")
        for file, blocks in patches.items():
            code = patch.ctx.format.patch(codes[file], blocks)
            if file_remap:
                file = file_remap[file]
            file.write_text(code)


empty = EmptyContext()
