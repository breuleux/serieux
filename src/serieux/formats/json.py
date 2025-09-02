import importlib
from pathlib import Path

from .abc import FileFormat

# Try installed JSON libraries in order of performance
# TODO: add msgspec? The interface is a little different.
preferences = [
    "orjson",
    "ujson",
    "json",
]

for modname in preferences:
    try:
        json = importlib.import_module(modname)
        break
    except ImportError:
        continue


class JSON(FileFormat):
    def load(self, f: Path):
        with open(f, "r", encoding="utf-8") as file:
            return json.load(file)

    def dump(self, f: Path, data):
        with open(f, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
