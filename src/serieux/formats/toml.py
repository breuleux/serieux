import tomllib
from pathlib import Path

from .abc import FileFormat


class TOML(FileFormat):
    def load(self, f: Path):
        with open(f, "rb") as file:
            return tomllib.load(file)

    def dump(self, f: Path, data):
        with open(f, "wb") as file:
            tomllib.dump(data, file)
