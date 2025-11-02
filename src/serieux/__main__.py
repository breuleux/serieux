import getpass
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import CommandLineArguments, TaggedUnion, deserialize, schema, serieux
from .auto import Auto
from .ctx import Patcher, empty
from .features.encrypt import EncryptionKey
from .features.fromfile import IncludeFile
from .features.prompt import Promptable
from .features.registered import Referenced
from .model import field_at

srx = serieux + IncludeFile()


def value_at(data, path):
    for part in path.split("."):
        if isinstance(data, Sequence):
            data = data[int(part)]
        elif isinstance(data, Mapping):  # pragma: no cover
            data = data[part]
        else:
            data = getattr(data, part)
    return data


def model_at(model, path):
    model = field_at(model, path)
    if model is None:  # pragma: no cover
        sys.exit(f"No model found at {path!r}")
    return model.type


@dataclass
class Schema:
    """Dump the JSON schema of a class."""

    # A module:symbol reference for the schema
    # [positional]
    model: Referenced[Any]

    # Output file
    # [option: -o]
    out: Path = None

    def __call__(self):
        sch = schema(self.model).compile()
        txt = json.dumps(sch, indent=4)
        if self.out:
            self.out.write_text(txt)
        else:
            print(txt)


def enter_password():  # pragma: no cover
    return getpass.getpass("Enter password: ")


@dataclass(kw_only=True)
class FileOperation:
    # A module:symbol reference for the schema
    # [alias: -m]
    model: Referenced[Any]

    # Encryption password
    # [alias: -p]
    password: str = None

    # Input file
    # [alias: -f]
    file: Path

    def load(self, base_ctx=empty):
        ctx = Promptable() + base_ctx
        if self.password:
            ctx += EncryptionKey(password=self.password)
        elif "SERIEUX_PASSWORD" in os.environ:
            ctx += EncryptionKey(password=os.environ["SERIEUX_PASSWORD"])
        else:  # pragma: no cover
            ctx += EncryptionKey(password=enter_password)
        return srx.deserialize(self.model, self.file, ctx)


@dataclass(kw_only=True)
class SelectableFileOperation(FileOperation):
    # Path to select
    select: str = ""

    def load(self, base_ctx=empty):
        result = super().load(base_ctx)
        if self.select:
            result = value_at(result, self.select)
        return result

    def get_model(self):
        return model_at(self.model, self.select) if self.select else self.model


@dataclass(kw_only=True)
class Dump(SelectableFileOperation):
    """Dump configuration."""

    # Format to dump into
    format: str = "yaml"

    # File to dump into
    # [alias: -o]
    out: Path = None

    def __call__(self):
        m = self.get_model()
        result = self.load()
        serialized = srx.dump(m, result, dest=self.out, format=self.format)
        if serialized is not None:
            print(serialized.strip())


@dataclass(kw_only=True)
class Check(SelectableFileOperation):
    """Check configuration (true/false)."""

    def __call__(self):
        try:
            data = self.load()
        except (AttributeError, ValueError, KeyError):
            print("nonexistent")
            exit(2)

        if data:
            print("true")
            exit(0)
        elif not data:
            print("false")
            exit(1)


@dataclass(kw_only=True)
class Patch(FileOperation):
    """Patch a configuration file for prompts and secrets."""

    # Output file (will modify inplace if omitted)
    # [alias: -o]
    out: Path = None

    def __call__(self):
        patcher = Patcher()
        self.load(base_ctx=patcher)
        remap = {self.file: self.out} if self.out else None
        patcher.apply_patches(file_remap=remap)

        if patcher.patches:
            print("\033[1;36mThe following patches were applied:\033[0m")
            for p in patcher.patches.values():
                print(
                    f"\033[1;33m[{'.'.join(str(x) for x in p.ctx.trail)}]\033[0m \033[1;32m{p.description}\033[0m"
                )
        else:  # pragma: no cover
            print("\033[1;36mNo patches were applied.\033[0m")


@dataclass(kw_only=True)
class Run:
    """Run a function or class."""

    # Reference to the function or class to run
    # [positional]
    func: Referenced[Any]

    # Function arguments
    # [positional: ...]
    args: list[str]

    def __call__(self):
        result = deserialize(Auto[self.func], CommandLineArguments(self.args))
        if callable(result):
            result = result()
        if result is not None:
            print(result)


@dataclass
class SerieuxCommand:
    """Do things with serieux configurations."""

    # The command to run
    command: TaggedUnion[Schema, Dump, Check, Patch, Run]

    def __call__(self):  # pragma: no cover
        self.command()


def main(argv=None):  # pragma: no cover
    sys.path.insert(0, str(Path.cwd()))

    if argv is None:
        argv = sys.argv[1:]

    cmd = deserialize(SerieuxCommand, CommandLineArguments(arguments=argv))
    cmd()


if __name__ == "__main__":  # pragma: no cover
    main()
