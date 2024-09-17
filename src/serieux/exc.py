import sys

from .proxy import Accessor, Source
from .utils import display_context


class ValidationExceptionGroup(ExceptionGroup):
    def derive(self, excs):
        return ValidationExceptionGroup(self.message, excs)

    def display(self, file=sys.stderr):
        for i, exc in enumerate(self.exceptions):
            exc.display(file=file, prefix=f"[#{i}] ")


class ValidationError(Exception):
    def __init__(self, message=None, *, exc=None, ctx=None):
        if message is None:
            message = f"{type(exc).__name__}: {exc}"
        super().__init__(message)
        self.exc = exc
        self.ctx = ctx

    @property
    def message(self):
        return self.args[0]

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
        acc = self.ctx.get(Accessor, "??")
        acc_string = str(acc) or "(at root)"
        location = self.ctx.get(Source, None)
        if location:
            (l1, c1), (l2, c2) = location.linecols
            lc = f"{l1}:{c1}-{l2}:{c2}" if l1 != l2 else f"{l1}:{c1}-{c2}"
            return f"{location.origin}:{lc} -- {type(self.exc).__qualname__}: {self.exc}"
        else:
            return f"At path {acc_string}: {type(self.exc).__qualname__}: {self.exc}"
