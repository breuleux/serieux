import json
import shutil
from dataclasses import dataclass

import pytest

from serieux import Serieux
from serieux.ctx import Patcher
from serieux.features.encrypt import Encrypt, EncryptionKey, Secret, crypt_prefix

featured = (Serieux + Encrypt)()
serialize = featured.serialize
deserialize = featured.deserialize


@pytest.fixture
def ekey():
    return EncryptionKey(password="sesame")


@pytest.fixture
def bad_ekey():
    return EncryptionKey(password="peanuts")


@pytest.fixture
def no_ekey():
    return EncryptionKey(password=None)


@dataclass
class User:
    name: str
    password: Secret[str]


@dataclass
class Account:
    username: str
    secrets: Secret[dict[str, str]]
    public_info: str


def test_basic_encryption_decryption(ekey):
    original_value = "secret_data"
    encrypted = ekey.encrypt(original_value)

    assert encrypted.startswith(crypt_prefix)
    assert original_value not in encrypted

    decrypted = ekey.decrypt(encrypted)
    assert decrypted == original_value


def test_secret_string_serialization(ekey):
    user = User(name="alice", password="super_secret")
    serialized = serialize(User, user, ekey)

    assert serialized["name"] == "alice"
    assert serialized["password"].startswith(crypt_prefix)
    assert "super_secret" not in json.dumps(serialized)

    deserialized = deserialize(User, serialized, ekey)
    assert deserialized == user


def test_secret_dict_serialization(ekey):
    account = Account(
        username="bob",
        secrets={"api_key": "abc123", "token": "xyz789"},
        public_info="This is public",
    )

    serialized = serialize(Account, account, ekey)

    assert serialized["username"] == "bob"
    assert serialized["public_info"] == "This is public"
    assert serialized["secrets"].startswith(crypt_prefix)

    serialized_str = json.dumps(serialized)
    assert "abc123" not in serialized_str
    assert "xyz789" not in serialized_str

    deserialized = deserialize(Account, serialized, ekey)
    assert deserialized == account


def test_wrong_password_decryption(ekey, bad_ekey):
    user = User(name="charlie", password="my_secret")

    serialized = serialize(User, user, ekey)

    # Try to deserialize with wrong password - should fail
    with pytest.raises(Exception):
        deserialize(User, serialized, bad_ekey)


def test_no_password_decryption(ekey, no_ekey):
    user = User(name="charlie", password="my_secret")

    serialized = serialize(User, user, ekey)

    with pytest.raises(Exception):
        deserialize(User, serialized, no_ekey)


def test_callable_password():
    calls = [0]

    def get_pw():
        calls[0] += 1
        return "letmein"

    users = [
        User(name="Åke", password="hemlighet1"),
        User(name="Linnéa", password="blomma2"),
        User(name="Gösta", password="skog3"),
        User(name="Måns", password="sol4"),
        User(name="Sigrid", password="norrsken5"),
    ]

    serialized = serialize(list[User], users, EncryptionKey(password=get_pw))
    assert not any(u.password in str(serialized) for u in users)
    assert calls == [1]


def test_missing_encryption_context():
    user = User(name="dave", password="secret")
    serialized = serialize(User, user)
    assert serialized["name"] == "dave"
    assert serialized["password"] == "secret"


def test_invalid_encrypted_data(ekey):
    """Test deserialization with invalid encrypted data."""
    invalid_data = {"name": "eve", "password": f"{crypt_prefix}invalid_encrypted_data"}
    with pytest.raises(Exception):
        deserialize(User, invalid_data, ekey)


def test_encryption_with_patcher(ekey, datapath, tmp_path):
    src = datapath / "userpass.yaml"
    dest = tmp_path / "userpass.yaml"
    shutil.copy(src, dest)

    patcher = Patcher()
    ctx = ekey + patcher
    user = deserialize(User, dest, ctx)
    assert user.name == "frank"
    assert user.password == "plain_text_secret"
    assert len(patcher.patches) > 0

    assert crypt_prefix not in dest.read_text()
    patcher.apply_patches()
    assert crypt_prefix in dest.read_text()

    patcher = Patcher()
    ctx = ekey + patcher
    user = deserialize(User, dest, ctx)
    assert user.name == "frank"
    assert user.password == "plain_text_secret"
    assert len(patcher.patches) == 0
