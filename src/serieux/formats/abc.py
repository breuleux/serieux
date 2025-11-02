from pathlib import Path


class FileFormat:  # pragma: no cover
    def locate(self, f: Path, trail: tuple[str]):
        return None

    def patch(self, source, patches):
        raise NotImplementedError(f"{type(self).__name__} does not implement `patch`")

    def loads(self, s: str):
        raise NotImplementedError(f"{type(self).__name__} does not implement `loads`")

    def dumps(self, data):
        raise NotImplementedError(f"{type(self).__name__} does not implement `dumps`")

    def load(self, f: Path):
        return self.loads(f.read_text())

    def dump(self, f: Path, data):
        f.write_text(self.dumps(data))

    @classmethod
    def serieux_from_string(cls, suffix):
        from . import registry

        return registry[suffix.lstrip(".")]
