from dataclasses import dataclass


@dataclass
class Loc:
    """Character-level source location within an argv list.

    When ``phantom=True`` the location does not point to real characters but
    to ``end`` imaginary characters inserted right *after* ``argv[arg_index]``
    in the rendered output, to indicate where something is *missing*.
    """

    argv: list[str]
    arg_index: int  # 0-based index into argv
    start: int  # char offset within argv[arg_index]  (0 if phantom)
    end: int  # exclusive end  (phantom width if phantom)
    prog: str | None = None  # program name shown dimmed before the arg line
    phantom: bool = False  # if True, insert phantom chars after argv[arg_index]
    phantom_char: str = " "  # character used for the phantom display area

    def render(self, message: str, color: bool = None) -> str:
        from .errors import render_all_errors

        return render_all_errors([(message, self)], color)

    def __add__(self, other: "Loc") -> "Loc":
        """Merge two locations within the same argv element."""
        assert self.argv is other.argv and self.arg_index == other.arg_index
        return Loc(
            self.argv,
            self.arg_index,
            min(self.start, other.start),
            max(self.end, other.end),
            self.prog,
        )


@dataclass
class LongOpt:
    """A --name or --name=value token.

    ``name_loc`` covers ``--name``.
    ``value`` / ``value_loc`` are set only when ``=`` is present.
    """

    name: str
    name_loc: Loc
    value: str | None = None
    value_loc: Loc | None = None


@dataclass
class ShortOpt:
    """A short-option cluster like ``-xyz`` or ``-x=val``.

    ``chars`` is the run of flag characters (e.g. ``'xyz'``).
    ``chars_loc`` covers just those characters (after the leading ``-``).
    ``value`` / ``value_loc`` are set only when ``=`` is present.
    """

    chars: str
    chars_loc: Loc
    value: str | None = None
    value_loc: Loc | None = None


@dataclass
class Value:
    """A bare positional value."""

    text: str
    loc: Loc


@dataclass
class ShortOptValue:
    """Tail of a short-option cluster used as a value (e.g. 'Alice' from '-nAlice').

    Distinct from Value so that option consumers can tell whether an inline
    value came from an explicit ``=val`` (Value) or from the remainder of a
    cluster (ShortOptValue).
    """

    text: str
    loc: Loc


@dataclass
class Separator:
    """The ``--`` end-of-options sentinel."""

    loc: Loc


Token = LongOpt | ShortOpt | Value | Separator


def tokenize(argv: list[str], prog: str = None) -> list[Token]:
    """Convert an argv list into a sequence of typed tokens with source locations.

    * ``--``        → :class:`Separator`; all following args become :class:`Value`.
    * ``--name``    → :class:`LongOpt` (``value=None``).
    * ``--name=v``  → :class:`LongOpt` (``value='v'``).
    * ``-x``        → :class:`ShortOpt` (``chars='x'``).
    * ``-xyz``      → :class:`ShortOpt` (``chars='xyz'``).
    * ``-x=v``      → :class:`ShortOpt` (``chars='x'``, ``value='v'``).
    * anything else → :class:`Value` (including bare ``-``).
    """
    tokens: list[Token] = []
    past_separator = False

    for idx, arg in enumerate(argv):

        def _loc(start: int, end: int, _i: int = idx) -> Loc:
            return Loc(argv, _i, start, end, prog=prog)

        if past_separator:
            tokens.append(Value(text=arg, loc=_loc(0, len(arg))))
            continue

        if arg == "--":
            tokens.append(Separator(loc=_loc(0, 2)))
            past_separator = True
            continue

        if arg.startswith("--"):
            body = arg[2:]
            if "=" in body:
                eq = body.index("=")
                name, val = body[:eq], body[eq + 1 :]
                tokens.append(
                    LongOpt(
                        name=f"--{name}",
                        name_loc=_loc(0, 2 + eq),
                        value=val,
                        value_loc=_loc(2 + eq + 1, len(arg)),
                    )
                )
            else:
                tokens.append(LongOpt(name=f"--{body}", name_loc=_loc(0, len(arg))))
            continue

        if arg.startswith("-") and len(arg) >= 2 and arg[1] != "-":
            chars_raw = arg[1:]
            if "=" in chars_raw:
                eq = chars_raw.index("=")
                chars, val = chars_raw[:eq], chars_raw[eq + 1 :]
                tokens.append(
                    ShortOpt(
                        chars=f"-{chars}",
                        chars_loc=_loc(1, 1 + eq),
                        value=val,
                        value_loc=_loc(1 + eq + 1, len(arg)),
                    )
                )
            else:
                tokens.append(ShortOpt(chars=f"-{chars_raw}", chars_loc=_loc(1, len(arg))))
            continue

        tokens.append(Value(text=arg, loc=_loc(0, len(arg))))

    return tokens
