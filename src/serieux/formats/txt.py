from pathlib import Path

from .abc import FileFormat


class Text(FileFormat):
    def load(self, f: Path):
        with open(f, "r", encoding="utf-8") as file:
            return file.read()

    def dump(self, f: Path, data):
        with open(f, "w", encoding="utf-8") as file:
            file.write(data)
