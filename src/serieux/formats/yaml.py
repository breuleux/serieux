from pathlib import Path

import yaml

from .abc import FileFormat


class YAML(FileFormat):
    def load(self, f: Path):
        return yaml.compose(f.read_text()) or {}

    def dump(self, f: Path, data):
        with open(f, "w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
