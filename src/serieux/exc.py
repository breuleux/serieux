import inspect
import re
import sys
from itertools import pairwise

from ovld import ovld
from ovld.medley import ABSENT

from .ctx import AccessPath, Context, locate
from .formats import FileSource


def _color(code, text):
    return f"\u001b[1m\u001b[{code}m{text}\u001b[0m"


def find_ctx(frame=None):
    frame = frame or sys._getframe(1)
    while frame:
        if "ctx" in frame.f_locals:
            if isinstance(ctx_val := frame.f_locals["ctx"], Context):
                return ctx_val
        frame = frame.f_back
    return None


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


def find_access_path(ctx):
    if isinstance(ctx, AccessPath):
        return ctx.access_path
    else:
        objstack = [
            (locs["t"], locs.get("obj", ABSENT))
            for frame in inspect.stack()
            if re.match(r"^((de)?serialize|schema)\[", frame.function)
            and "t" in (locs := frame.frame.f_locals)
        ]
        links = [
            lnk
            for (t1, obj1), (t2, obj2) in pairwise(reversed(objstack))
            if (lnk := find_link(obj1, obj2))
        ]
        return links


def extract_information(ctx=None, frame=None):
    frame = frame or sys._getframe(1)
    locs = []
    ap = []
    above = None
    func = None
    while frame:
        lcls = frame.f_locals
        ctx = lcls.get("ctx", ctx)
        if isinstance(ctx, AccessPath):
            ap = [*ctx.access_path, *reversed(ap)]
            locs = [locate(ctx), *reversed(locs)]
            return (func or "<serieux>", ap, locs)
        elif ctx and (m := re.match(r"^((?:de)?serialize|schema)\[", frame.f_code.co_name)):
            func = m.groups()[0]
            t1, obj1 = lcls.get("t", ABSENT), lcls.get("obj", ABSENT)
            if isinstance(obj1, FileSource):
                if obj1.field:  # pragma: no cover
                    ap.extend(reversed(obj1.field.split(".")))
                loc = obj1.format.locate(obj1.path, list(reversed(ap)))
                locs.append(loc)
            if above is not None:
                _, obj2 = above
                if lnk := find_link(obj1, obj2):
                    ap.append(lnk)
            above = t1, obj1
        frame = frame.f_back
    ap.reverse()
    locs.reverse()
    return func, ap, locs


def display_context_information(
    message="An error happened in serieux.{func} at location {access_path}",
    *,
    ctx=None,
    exc=None,
    frame=None,
    show_source=True,
    file=sys.stderr,
    **kwargs,
):
    if exc is not None:
        if isinstance(exc, IndividualSerieuxError) and exc.ctx:  # pragma: no cover
            ctx = exc.ctx
        else:
            tb = exc.__traceback__
            while tb:
                frame = tb.tb_frame
                tb = tb.tb_next
    func, acc, locs = extract_information(ctx, frame)
    if func is None:  # pragma: no cover
        return
    access_string = "".join([f".{field}" for field in acc]) if acc else "(at root)"
    print(message.format(access_path=_color(33, access_string), func=func), file=file)
    if show_source and locs:
        for location in locs:
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
    while end >= len(lines) or not lines[end].strip():  # pragma: no cover
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


def context_string(
    ctx,
    access_string,
    message,
    show_source=True,
    source_context=1,
    indent=0,
    ellipsis_cutoff=3,
):
    n = 3 + indent
    return_lines = [f"{_color(33, access_string)}: {message}"]
    if show_source and (location := locate(ctx)):
        (l1, c1), (l2, c2) = location.linecols
        if c2 == 0:
            l2 -= 1
            c2 = 10_000_000_000_000
        lines = location.whole_text.split("\n")
        start = l1 - source_context
        while start < 0 or not lines[start].strip():
            start += 1
        end = l2 + source_context
        while end >= len(lines) or not lines[end].strip():  # pragma: no cover
            end -= 1

        return_lines.append(f"{'':{indent}}@ {location.source}:{l1 + 1}")
        for li in range(start, end + 1):
            line = lines[li]
            if li == l2 and not line.strip():  # pragma: no cover
                break
            if li == l1 + ellipsis_cutoff and li < l2:
                return_lines.append(f"{'':{n}}  ...")
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

            return_lines.append(f"{li + 1:{n}}: {line}")
    return "\n".join(return_lines)


def display_context(*args, file=sys.stderr, **kwargs):
    cs = context_string(*args, **kwargs)
    print(cs, file=file)


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
        self.ctx = ctx or find_ctx()
        acc = find_access_path(self.ctx)
        self.access_string = "".join([f".{field}" for field in acc]) if acc else "(at root)"

    @property
    def message(self):
        return self.args[0]

    def __str__(self):
        if location := locate(self.ctx):
            (l1, c1), (l2, c2) = location.linecols
            lc = f"{l1}:{c1}-{l2}:{c2}" if l1 != l2 else f"{l1}:{c1}-{c2}"
            return f"{location.source}:{lc} -- {self.message}"
        else:
            return f"At path {self.access_string}: {self.message}"


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


@ovld
def display(exc: IndividualSerieuxError, file=sys.stderr):
    display_context(
        exc.ctx,
        access_string=exc.access_string,
        show_source=True,
        message=exc.message,
        file=file,
        indent=2,
    )


@ovld
def display(exc: ValidationExceptionGroup, file=sys.stderr):
    for i, subexc in enumerate(exc.exceptions):
        print(f"[#{i}] ", end="", file=file)
        display(subexc, file)


@ovld
def display(exc: Exception, file=sys.stderr):
    display_context_information(
        f"At path {{access_path}}: {type(exc).__name__}: {exc}", exc=exc, file=file
    )
