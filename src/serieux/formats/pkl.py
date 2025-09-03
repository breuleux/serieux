import pickle
from pathlib import Path

from .abc import FileFormat


class PKL(FileFormat):
    def load(self, f: Path):
        return pickle.loads(f.read_bytes())

    def dump(self, f: Path, data):
        f.write_bytes(pickle.dumps(data))
