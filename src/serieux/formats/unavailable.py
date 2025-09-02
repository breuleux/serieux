from .abc import FileFormat


class Unavailable(FileFormat):  # pragma: no cover
    def __init__(self, suffix, required_import):
        self.suffix = suffix
        self.required_import = required_import
        self.message = f"Support for '{self.suffix}' files requires the '{self.required_import}' package to be installed."

    def load(self, f):
        raise ImportError(self.message)

    def dump(self, f, data):
        raise ImportError(self.message)
