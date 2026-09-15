import getpass
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import deserialize, schema, serieux
from .auto import Auto
from .ctx import Patcher, empty
from .features.clargs import CommandLineArguments
from .features.encrypt import EncryptionKey
from .features.fromfile import IncludeFile
from .features.prompt import Promptable
from .features.registered import Referenced
from .features.tagset import TagDict, TaggedSubclass, TaggedUnion, tag_field
from .formats import FileSource
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

    # Example file
    # [positional]
    file: Path = None

    # A module:symbol reference for the schema
    # [alias: -m]
    model: Referenced[Any] = None

    # Output file
    # [option: -o]
    out: Path = None

    def __call__(self):
        model = self.model

        if model is None and self.file is None:  # pragma: no cover
            sys.exit("Must provide either file or model")
        elif model is None:
            self.file = FileSource(self.file)
            data = self.file.load()
            if tag_field not in data:
                sys.exit(f"Model file should define a {tag_field} field")
            tag = data[tag_field]
            raw_model = deserialize(Referenced[Any], tag)
            model = raw_model @ TagDict({tag: raw_model})

        sch = schema(model).compile()
        txt = json.dumps(sch, indent=4)
        if self.out:
            self.out.write_text(txt)
        else:
            print(txt)


def enter_password():  # pragma: no cover
    return getpass.getpass("Enter password: ")


@dataclass(kw_only=True)
class FileOperation:
    # Input file
    # [positional]
    file: FileSource

    # A module:symbol reference for the schema
    # [alias: -m]
    model: Referenced[Any] = TaggedSubclass[Any]

    # Encryption password
    # [alias: -p]
    password: str = None

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
            sys.exit(2)

        if data:
            print("true")
            sys.exit(0)
        elif not data:
            print("false")
            sys.exit(1)


@dataclass(kw_only=True)
class Patch(FileOperation):
    """Patch a configuration file for prompts and secrets."""

    # Output file (will modify inplace if omitted)
    # [alias: -o]
    out: Path = None

    def __call__(self):
        patcher = Patcher()
        self.load(base_ctx=patcher)
        remap = {self.file.path: self.out} if self.out else None
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
class Call:
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


@dataclass(kw_only=True)
class Run:
    """Run an object defined in a configuration."""

    # Definition of the object to run
    # [positional]
    file: Path

    def __call__(self):
        obj = deserialize(TaggedSubclass[object], self.file)
        return obj()


@dataclass(kw_only=True)
class Interact:
    """Interact with an object defined in a configuration."""

    # Definition of the object to interact with
    # [positional]
    file: Path

    def __call__(self):  # pragma: no cover
        import code

        print("=" * 30)
        print(self.file.read_text().rstrip("\n"))
        print("=" * 30)
        obj = deserialize(TaggedSubclass[object], self.file)
        print(">>> obj")
        print(obj)
        code.interact(local={"obj": obj}, banner="")


@dataclass
class SerieuxCommand:
    """Do things with serieux configurations."""

    # The command to run
    command: TaggedUnion[Schema, Dump, Check, Patch, Call, Run, Interact]

    def __call__(self):  # pragma: no cover
        result = self.command()
        if result is not None:
            print(result)


def main(argv=None):  # pragma: no cover
    sys.path.insert(0, str(Path.cwd()))

    if argv is None:
        argv = sys.argv[1:]

    cmd = deserialize(SerieuxCommand, CommandLineArguments(arguments=argv))
    cmd()


if __name__ == "__main__":  # pragma: no cover
    main()
