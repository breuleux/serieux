from .abc import FileFormat


class Text(FileFormat):
    def loads(self, s: str):
        return s

    def dumps(self, data):
        return data
