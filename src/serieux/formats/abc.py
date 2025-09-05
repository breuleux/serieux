from pathlib import Path


class FileFormat:  # pragma: no cover
    def locate(self, f: Path, access_path: tuple[str]):
        return None

    def patch(self, source, patches):
        raise NotImplementedError(f"{type(self).__name__} does not implement `patch`")

    def load(self, f: Path):
        raise NotImplementedError(f"{type(self).__name__} does not implement `load`")

    def dump(self, f: Path, data):
        raise NotImplementedError(f"{type(self).__name__} does not implement `dump`")

    @classmethod
    def serieux_from_string(cls, suffix):
        from . import registry

        return registry[suffix.lstrip(".")]
