import sys


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

    def __str__(self):
        acc = getattr(self.ctx, "access_path", [(None, "???")])
        acc_string = "".join([f".{field}" for obj, field in acc]) if acc else "(at root)"
        return f"At path {acc_string}: {self.message}"
