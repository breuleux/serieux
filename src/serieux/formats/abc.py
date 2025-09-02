from pathlib import Path


class FileFormat:  # pragma: no cover
    def load(self, f: Path):
        raise NotImplementedError(f"{type(self).__name__} does not implement `load`")

    def dump(self, f: Path, data):
        raise NotImplementedError(f"{type(self).__name__} does not implement `dump`")
