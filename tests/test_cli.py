from dataclasses import dataclass

import cryptography
import pytest

from serieux.__main__ import (
    Check,
    Dump,
    Patch,
    Run,
    Schema,
    model_at,
    value_at,
)
from serieux.features.encrypt import crypt_prefix
from tests.definitions import Pig, Point, World
from tests.features.test_encrypt import User


def test_value_at_dict():
    data = {"a": {"b": {"c": 42}}}
    assert value_at(data, "a.b.c") == 42


def test_value_at_list():
    data = {"items": [{"name": "first"}, {"name": "second"}]}
    assert value_at(data, "items.1.name") == "second"


def test_value_at_object():
    point = Point(x=10, y=20)
    data = {"point": point}
    assert value_at(data, "point.x") == 10
    assert value_at(data, "point.y") == 20


def test_model_at():
    assert model_at(Point, "x") is int
    assert model_at(list[Point], "0.x") is int


def test_dump_command(capsys, datapath, file_regression):
    dumper = Dump(
        model=World,
        file=datapath / "world.yaml",
        format="yaml",
        password="NOT_USED",
    )
    dumper()
    captured = capsys.readouterr()
    file_regression.check(captured.out)


def test_dump_command_out(tmp_path, datapath, file_regression):
    out_file = tmp_path / "dump.yaml"
    dumper = Dump(
        model=World,
        file=datapath / "world.yaml",
        format="yaml",
        password="NOT_USED",
        out=out_file,
    )
    dumper()
    assert out_file.exists()
    content = out_file.read_text()
    file_regression.check(content)


def test_dump_command_encrypted(tmp_path, datapath):
    out_file = tmp_path / "dump.yaml"
    dumper = Dump(
        model=list[User],
        file=datapath / "users-encrypted.yaml",
        format="yaml",
        password="gaga",
        out=out_file,
    )
    dumper()
    content = out_file.read_text()
    assert "super_secret" in content
    assert "abc123" in content
    assert "letmein" in content


def test_dump_command_encrypted_env_password(tmp_path, datapath, monkeypatch):
    out_file = tmp_path / "dump.yaml"
    monkeypatch.setenv("SERIEUX_PASSWORD", "gaga")
    dumper = Dump(
        model=list[User],
        file=datapath / "users-encrypted.yaml",
        format="yaml",
        out=out_file,
    )
    dumper()
    content = out_file.read_text()
    assert "super_secret" in content
    assert "abc123" in content
    assert "letmein" in content


def test_dump_command_wrong_password(datapath):
    dumper = Dump(
        model=list[User],
        file=datapath / "users-encrypted.yaml",
        format="yaml",
        password="WRONG",
    )
    with pytest.raises(cryptography.fernet.InvalidToken):
        dumper()


def test_check_command(datapath):
    for sel, code in [("weight", 0), ("beautiful", 1), ("inexistent", 2)]:
        checker = Check(
            model=Pig,
            file=datapath / "beastfly.yaml",
            select=sel,
            password="NOT_USED",
        )

        with pytest.raises(SystemExit) as exc:
            checker()
        assert exc.value.code == code


def test_schema_command(capsys, file_regression):
    schema_cmd = Schema(model=World)
    schema_cmd()
    captured = capsys.readouterr()
    file_regression.check(captured.out)


def test_schema_command_out(tmp_path, file_regression):
    out_file = tmp_path / "schema.json"
    schema_cmd = Schema(model=World, out=out_file)
    schema_cmd()
    assert out_file.exists()
    content = out_file.read_text()
    file_regression.check(content)


def test_patch_command(tmp_path, datapath):
    out_file = tmp_path / "encrypted.yaml"
    patcher = Patch(
        model=list[User],
        file=datapath / "users.yaml",
        password="gaga",
        out=out_file,
    )
    patcher()
    assert out_file.exists()
    content = out_file.read_text()

    assert "super_secret" not in content
    assert "abc123" not in content
    assert "letmein" not in content

    assert crypt_prefix in content


def test_patch_command_inplace(tmp_path, datapath):
    out_file = tmp_path / "encrypted.yaml"
    out_file.write_bytes((datapath / "users.yaml").read_bytes())

    content = out_file.read_text()
    assert "super_secret" in content
    assert "abc123" in content
    assert "letmein" in content
    assert crypt_prefix not in content

    patcher = Patch(
        model=list[User],
        file=out_file,
        password="gaga",
        out=out_file,
    )
    patcher()

    content = out_file.read_text()
    assert "super_secret" not in content
    assert "abc123" not in content
    assert "letmein" not in content
    assert crypt_prefix in content


def addnums(x: int, y: int, /):
    return x + y


def test_run_command(capsys):
    runner = Run(
        func=addnums,
        args=["6", "7"],
    )
    runner()
    captured = capsys.readouterr()
    assert captured.out.strip() == "13"


@dataclass
class Multiplier:
    left: int
    right: int

    def __call__(self):
        return self.left * self.right


def test_run_command_dataclass(capsys):
    runner = Run(
        func=Multiplier,
        args=["--left", "6", "--right", "7"],
    )
    runner()
    captured = capsys.readouterr()
    assert captured.out.strip() == "42"
