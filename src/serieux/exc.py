from serieux.proxy import Accessor


class ValidationExceptionGroup(ExceptionGroup):
    def derive(self, excs):
        return ValidationExceptionGroup(self.message, excs)


class ValidationError(Exception):
    def __init__(self, exc, ctx=None):
        super().__init__()
        self.exc = exc
        self.ctx = ctx

    def __str__(self):
        acc = self.ctx.get(Accessor, "??")
        return f"At path {acc}: {type(self.exc).__qualname__}: {self.exc}"
