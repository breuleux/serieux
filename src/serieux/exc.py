import sys

from .ctx import Context


def _color(code, text):
    return f"\u001b[1m\u001b[{code}m{text}\u001b[0m"


def access_string(ctx):
    acc = getattr(ctx, "access_path", ["???"])
    return "".join([f".{field}" for field in acc]) if acc else "(at root)"


def context_string(
    ctx,
    message,
    show_source=True,
    source_context=1,
    indent=0,
    ellipsis_cutoff=3,
):
    n = 3 + indent
    acc_string = access_string(ctx)
    return_lines = [f"{_color(33, acc_string)}: {message}"]
    if show_source and (location := getattr(ctx, "location", None)):
        (l1, c1), (l2, c2) = location.linecols
        if c2 == 0:
            l2 -= 1
            c2 = 10_000_000_000_000
        lines = location.code.split("\n")
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


def display_context(*args, file=sys.stdout, **kwargs):
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
        self.ctx = ctx
        if self.ctx is None:
            frame = sys._getframe(1)
            while frame:
                if "ctx" in frame.f_locals:
                    if isinstance(ctx_val := frame.f_locals["ctx"], Context):
                        self.ctx = ctx_val
                        break
                frame = frame.f_back

    @property
    def message(self):
        return self.args[0]

    def access_string(self):
        return access_string(self.ctx)

    def display(self, file=sys.stderr, prefix=""):
        print(prefix, end="", file=file)
        display_context(
            self.ctx,
            show_source=True,
            message=self.message,
            file=file,
            indent=2,
        )

    def __str__(self):
        location = getattr(self.ctx, "location", None)
        if location:
            (l1, c1), (l2, c2) = location.linecols
            lc = f"{l1}:{c1}-{l2}:{c2}" if l1 != l2 else f"{l1}:{c1}-{c2}"
            return f"{location.source}:{lc} -- {self.message}"
        else:
            return f"At path {access_string(self.ctx)}: {self.message}"


class NotGivenError(IndividualSerieuxError):
    pass


class ValidationExceptionGroup(SerieuxError, ExceptionGroup):
    def derive(self, excs):  # pragma: no cover
        return ValidationExceptionGroup(self.message, excs)

    def display(self, file=sys.stderr):
        for i, exc in enumerate(self.exceptions):
            exc.display(file=file, prefix=f"[#{i}] ")


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
