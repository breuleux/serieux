import sys

from .tokenize import Loc


class ParseError(Exception):
    """Holds one or more located error messages, rendered together."""

    def __init__(self, message: str, loc: Loc = None):
        super().__init__(message)
        self.loc = loc
        self._items: list[tuple[str, Loc | None]] = [(message, loc)]

    @classmethod
    def _from_items(cls, items: list[tuple[str, Loc | None]]) -> "ParseError":
        obj = cls.__new__(cls)
        first_msg = items[0][0] if items else ""
        first_loc = items[0][1] if items else None
        Exception.__init__(obj, first_msg)
        obj.loc = first_loc
        obj._items = list(items)
        return obj

    def __str__(self) -> str:
        return render_all_errors(self._items)


def _colorize_labeled(chars: list[str], err_col: str, reset: str) -> str:
    """Join underline chars, wrapping every non-space run in ANSI error color."""
    if not err_col:
        return "".join(chars)
    result: list[str] = []
    in_err = False
    for ch in chars:
        if ch != " " and not in_err:
            result.append(err_col)
            in_err = True
        elif ch == " " and in_err:
            result.append(reset)
            in_err = False
        result.append(ch)
    if in_err:
        result.append(reset)
    return "".join(result)


def render_all_errors(
    items: list[tuple[str, "Loc | None"]],
    color: bool = None,
) -> str:
    """Render a list of ``(message, loc)`` pairs.

    Each item is listed as ``a. message``, ``b. message``, … and its span in
    the arg line is underlined with ``^…^X`` where X is the assigned letter.
    Items without a loc still receive a letter in the listing but have no
    underline.  Phantom spans insert extra chars right after their token.
    """
    if color is None:
        color = sys.stderr.isatty()
    if not items:
        return ""

    # Assign a letter to each item (all items get a letter for consistency)
    letters = [chr(ord("a") + i) for i in range(len(items))]

    # Build message listing
    message_lines = [f"{letter}. {msg}" for letter, (msg, _) in zip(letters, items)]

    # Find the first item that has a loc (for argv / prog context)
    first_loc = next((loc for _, loc in items if loc is not None), None)
    if first_loc is None:
        return "\n".join(message_lines)

    argv = first_loc.argv
    prog = first_loc.prog

    # Lettered spans: only items that have a loc
    lettered: list[tuple[str, "Loc"]] = [
        (letter, loc) for letter, (_, loc) in zip(letters, items) if loc is not None
    ]

    err_col = "\033[1;31m" if color else ""
    dim = "\033[2m" if color else ""
    reset = "\033[0m" if color else ""

    # Determine phantom width, display char, and active ranges per arg index.
    # Active ranges are positions [start, end) within the phantom area that are
    # covered by a label; gaps between them become plain spaces in the display.
    phantom_width: dict[int, int] = {}
    phantom_char_for: dict[int, str] = {}
    phantom_active: dict[int, list[tuple[int, int]]] = {}
    for _, loc in lettered:
        if loc.phantom:
            phantom_width[loc.arg_index] = max(phantom_width.get(loc.arg_index, 0), loc.end)
            phantom_char_for[loc.arg_index] = loc.phantom_char
            phantom_active.setdefault(loc.arg_index, []).append((loc.start, loc.end))

    # Build plain display (for offset math) and colored display (for rendering).
    # Non-space phantom chars get an extra leading space and are rendered grey;
    # positions not covered by any active range become plain spaces.
    # phant_offsets is a dict so it can also hold "trailing" phantoms whose
    # arg_index >= len(argv) (e.g. when argv is empty).
    real_offsets: list[int] = []
    phant_offsets: dict[int, int | None] = {}
    plain_parts: list[str] = []
    color_parts: list[str] = []
    pos = 0
    for i, arg in enumerate(argv):
        real_offsets.append(pos)
        plain_parts.append(arg)
        color_parts.append(arg)
        pos += len(arg)
        pw = phantom_width.get(i, 0)
        pc = phantom_char_for.get(i, " ")
        if pw:
            if pc != " ":
                active = set()
                for s, e in phantom_active.get(i, []):
                    active.update(range(s, e))
                chars = "".join(pc if j in active else " " for j in range(pw))
                plain_parts.append(" " + chars)
                color_parts.append(" " + dim + chars + reset)
                phant_offsets[i] = pos + 1
                pos += 1 + pw
            else:
                plain_parts.append(" " * pw)
                color_parts.append(" " * pw)
                phant_offsets[i] = pos
                pos += pw
        else:
            phant_offsets[i] = None
        if i < len(argv) - 1:
            plain_parts.append(" ")
            color_parts.append(" ")
            pos += 1

    # Trailing phantoms: arg_index >= len(argv).  These are appended after all
    # real args (or are the entire display when argv is empty).
    for idx in sorted(
        {loc.arg_index for _, loc in lettered if loc.phantom and loc.arg_index >= len(argv)}
    ):
        pw = phantom_width.get(idx, 0)
        pc = phantom_char_for.get(idx, " ")
        if not pw:
            phant_offsets[idx] = None
            continue
        active = set()
        for s, e in phantom_active.get(idx, []):
            active.update(range(s, e))
        chars = "".join(pc if j in active else " " for j in range(pw))
        if pos > 0:  # separate from preceding real args
            plain_parts.append(" ")
            color_parts.append(" ")
            pos += 1
        if pc != " ":
            plain_parts.append(chars)
            color_parts.append(dim + chars + reset)
        else:
            plain_parts.append(chars)
            color_parts.append(chars)
        phant_offsets[idx] = pos
        pos += pw

    display = "".join(plain_parts)
    display_color = "".join(color_parts)
    uc = [" "] * len(display)

    for letter, loc in lettered:
        if loc.phantom:
            po = phant_offsets[loc.arg_index]
            if po is None:
                continue
            a, b = po + loc.start, po + loc.end
        else:
            a = real_offsets[loc.arg_index] + loc.start
            b = real_offsets[loc.arg_index] + loc.end
        a, b = max(0, a), min(b, len(uc))
        if b <= a:
            continue
        for j in range(a, b - 1):
            uc[j] = "^"
        uc[b - 1] = letter  # last char of span is the letter label

    underline = _colorize_labeled(uc, err_col, reset)

    if prog:
        prefix = len(prog) + 1
        line = f"{dim}{prog}{reset} {display_color}"
        under = " " * prefix + underline
    else:
        line = display_color
        under = underline

    header = "\n".join(message_lines)
    return f"{header}\n\n  {line}\n  {under}"
