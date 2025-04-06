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

    def access_string(self):
        acc = getattr(self.ctx, "access_path", [(None, "???")])
        return "".join([f".{field}" for obj, field in acc]) if acc else "(at root)"

    def display(self, file=sys.stderr, prefix=""):
        print(prefix, end="", file=file)
        print(str(self), file=file)

    def __str__(self):
        return f"At path {self.access_string()}: {self.message}"
