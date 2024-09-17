import sys

from ovld import ovld, recurse

from .model import Model
from .proxy import Accessor, Proxy, Source


def _color(code, text):
    return f"\u001b[1m\u001b[{code}m{text}\u001b[0m"


def context_string(
    obj,
    message,
    show_source=True,
    source_context=1,
    indent=0,
    ellipsis_cutoff=3,
):
    n = 3 + indent
    if isinstance(obj, Proxy):
        ctx = obj._self_ann
    elif isinstance(obj, dict):
        ctx = obj
    else:
        raise Exception("obj should be a Proxy or a dict")
    acc = ctx.get(Accessor, "??")
    acc_string = str(acc) or "(at root)"
    return_lines = [f"{_color(33, acc_string)}: {message}"]
    if show_source and (location := ctx.get(Source, None)):
        (l1, c1), (l2, c2) = location.linecols
        if c2 == 0:
            l2 -= 1
            c2 = 10_000_000_000_000
        lines = location.source.split("\n")
        start = l1 - source_context
        while start < 0 or not lines[start].strip():
            start += 1
        end = l2 + source_context
        while end >= len(lines) or not lines[end].strip():
            end -= 1

        return_lines.append(f"{'':{indent}}@ {location.origin}:{l1 + 1}")
        for li in range(start, end + 1):
            line = lines[li]
            if li == l2 and not line.strip():
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


@ovld
def typename(t: type):
    if issubclass(t, Proxy):
        return recurse(t._self_cls)
    else:
        return t.__qualname__


@ovld
def typename(t: Model):  # noqa: F811
    return f"{recurse(t.original_type)} ({type(t).__qualname__})"


@ovld
def typename(t: object):  # noqa: F811
    return repr(t)
