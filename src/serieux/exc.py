import re
import sys
from dataclasses import dataclass, field

from ovld import ovld
from ovld.medley import ABSENT

from .ctx import Context, Location, Trail, locate
from .formats import FileSource


@dataclass
class ContextInformation:
    func: str = None
    path: list[str] = field(default_factory=list)
    locs: list[Location] = field(default_factory=list)
    ctx: Context = None

    @property
    def trail_string(self):
        return "".join([f".{field}" for field in self.path]) if self.path else "(at root)"


def _color(code, text):
    return f"\u001b[1m\u001b[{code}m{text}\u001b[0m"


@ovld
def find_link(o1: dict, o2):
    for k, v in o1.items():
        if v is o2:
            return k
    return None


@ovld
def find_link(o1: list, o2):
    for i, v in enumerate(o1):
        if v is o2:
            return str(i)
    return None


@ovld
def find_link(o1, o2):
    try:
        v1 = vars(o1)
    except TypeError:
        return None
    return find_link(v1, o2)


def extract_information(ctx=None, frame=None):
    frame = frame or sys._getframe(1)
    ci = ContextInformation(ctx=ctx)

    def _fast_path():
        ci.func = ci.func or "<serieux>"
        ci.path[:0] = ci.ctx.trail
        if loc := locate(ci.ctx):
            ci.locs.insert(0, loc)
        return ci

    if isinstance(ci.ctx, Trail):
        return _fast_path()

    above = None
    while frame:
        lcls = frame.f_locals
        ci.ctx = lcls.get("ctx", ci.ctx)
        if isinstance(ci.ctx, Trail):
            return _fast_path()
        elif ci.ctx and (m := re.match(r"^((?:de)?serialize|schema)\[", frame.f_code.co_name)):
            ci.func = m.groups()[0]
            t1, obj1 = lcls.get("t", ABSENT), lcls.get("obj", ABSENT)
            obj2 = None
            if above is not None:
                _, obj2 = above
                if lnk := find_link(obj1, obj2):
                    ci.path.insert(0, lnk)
            if obj1 is not obj2 and isinstance(obj1, FileSource):
                try:
                    fp = obj1.field.split(".") if obj1.field else []
                    loc = obj1.format.locate(obj1.path, [*fp, *ci.path])
                    ci.locs.insert(0, loc)
                except FileNotFoundError:
                    pass
            above = t1, obj1
        frame = frame.f_back
    return ci


def display_context_information(
    template="An error happened in serieux.{func} at location {trail}",
    *,
    ctx=None,
    exc=None,
    frame=None,
    show_source=True,
    file=sys.stderr,
    message="ERROR",
    **kwargs,
):
    ci = None
    if exc is not None:
        if isinstance(exc, IndividualSerieuxError) and exc.ctx:
            ctx = exc.ctx
            ci = exc.info
        elif isinstance(exc, ValidationExceptionGroup):  # pragma: no cover
            display(exc)
            return
        else:
            tb = exc.__traceback__
            while tb:
                frame = tb.tb_frame
                tb = tb.tb_next
    ci = ci or extract_information(ctx, frame)
    if ci.func is None:  # pragma: no cover
        return
    print(
        template.format(trail=_color(33, ci.trail_string), func=ci.func, message=message),
        file=file,
    )
    if show_source and ci.locs:
        for location in ci.locs:
            display_location(location, file=file, **kwargs)


def display_location(location, source_context=1, indent=0, ellipsis_cutoff=3, file=sys.stderr):
    width = 3 + indent
    (l1, c1), (l2, c2) = location.linecols
    if c2 == 0:
        l2 -= 1
        c2 = 10_000_000_000_000
    lines = location.whole_text.split("\n")
    start = l1 - source_context
    while start < 0 or not lines[start].strip():
        start += 1
    end = l2 + source_context
    while end >= len(lines) or not lines[end].strip():
        end -= 1

    print(f"{'':{indent}}@ {location.source.absolute()}:{l1 + 1}", file=file)
    for li in range(start, end + 1):
        line = lines[li]
        if li == l2 and not line.strip():  # pragma: no cover
            break
        if li == l1 + ellipsis_cutoff and li < l2:
            print(f"{'':{width}}  ...", file=file)
            continue
        elif li > l1 + ellipsis_cutoff and li < l2:
            continue

        hls = hle = 0
        if li == l1:
            hls = c1
        if li >= l1 and li < l2:
            hle = len(line)
        if li == l2:
            hle = c2

        if hls or hle:
            line = line[:hls] + _color(31, line[hls:hle]) + line[hle:]

        print(f"{li + 1:{width}}: {line}", file=file)


def merge_errors(*errors):
    collected = []
    for err in errors:
        if isinstance(err, ExceptionGroup):
            collected.extend(err.exceptions)
        elif isinstance(err, Exception):
            collected.append(err)
    return ValidationExceptionGroup("Some errors occurred", collected) if collected else None


class SerieuxError(Exception):
    pass


class IndividualSerieuxError(SerieuxError):
    def __init__(self, message=None, *, ctx=None):
        super().__init__(message)
        self.info = extract_information(ctx)
        self.ctx = self.info.ctx

    @property
    def message(self):
        return self.args[0]

    def __str__(self):
        if location := locate(self.ctx):
            (l1, c1), (l2, c2) = location.linecols
            lc = f"{l1}:{c1}-{l2}:{c2}" if l1 != l2 else f"{l1}:{c1}-{c2}"
            return f"{location.source}:{lc} -- {self.message}"
        else:
            return f"At path {self.info.trail_string}: {self.message}"


class NotGivenError(IndividualSerieuxError):
    pass


class ValidationExceptionGroup(SerieuxError, ExceptionGroup):
    def derive(self, excs):  # pragma: no cover
        return ValidationExceptionGroup(self.message, excs)


class ValidationError(IndividualSerieuxError):
    def __init__(self, message=None, *, exc=None, ctx=None):
        if message is None:
            message = f"{type(exc).__name__}: {exc}"
        super().__init__(message=message, ctx=ctx)
        self.exc = exc


class SchemaError(IndividualSerieuxError):
    def __init__(self, message=None, *, exc=None, ctx=None):
        if message is None:  # pragma: no cover
            message = f"{type(exc).__name__}: {exc}"
        super().__init__(message=message, ctx=ctx)
        self.exc = exc


def display(exc, file=sys.stderr):
    if isinstance(exc, ValidationExceptionGroup):
        for i, subexc in enumerate(exc.exceptions):
            print(f"[#{i}] ", end="", file=file)
            display(subexc, file)
    else:
        if isinstance(exc, IndividualSerieuxError):
            msg = exc.message
        else:
            msg = f"{type(exc).__name__}: {exc}"
        display_context_information(
            "{trail}: {message}",
            exc=exc,
            file=file,
            message=msg,
            indent=2,
        )
