import base64
import json
from dataclasses import dataclass
from hashlib import sha256

from cryptography.fernet import Fernet, InvalidToken
from ovld import Medley, call_next
from ovld.dependent import Regexp

from serieux import Context, NewTag, Serieux, deserialize, serialize

##################
# Implementation #
##################


Secret = NewTag["Secret"]


class EncryptionKey(Context):
    password: str
    key: Fernet = None

    def __post_init__(self):
        encoded = base64.b64encode(sha256(self.password.encode()).digest())
        self.key = Fernet(encoded)

    def encrypt(self, value):
        encrypted = self.key.encrypt(json.dumps(value).encode("utf8")).decode("utf8")
        return f"~CRYPT~{encrypted}"

    def decrypt(self, encrypted: str):
        return json.loads(self.key.decrypt(encrypted.lstrip("~CRYPT~")))


@Serieux.extend
class Encrypt(Medley):
    def serialize(self, t: type[Secret], obj: object, ctx: EncryptionKey):
        result = call_next(Secret.strip(t), obj, ctx - EncryptionKey)
        return ctx.encrypt(result)

    def deserialize(self, t: type[Secret], obj: Regexp[r"^~CRYPT~.*"], ctx: EncryptionKey):
        obj = ctx.decrypt(obj)
        return call_next(Secret.strip(t), obj, ctx - EncryptionKey)


#################
# Demonstration #
#################


@dataclass
class User:
    name: str
    passwords: Secret[dict[str, str]]


def show(title, value):
    print(f"\033[1;33m{title:15}\033[0m{value}")


autoinput = {
    "Password: ": "bonjour",
    "Enter password again: ": "bonjour",
}.__getitem__


def main(input=autoinput):
    password = input("Password: ")
    ctx = EncryptionKey(password)

    olivier = User(name="olivier", passwords={"google": "tobeornottobeevil", "apple": "banana"})
    show("Original", olivier)

    serial = serialize(User, olivier, ctx)
    show("Serialized", serial)

    # Our secrets are safe!
    assert "tobeornottobeevil" not in json.dumps(serial)
    assert "banana" not in json.dumps(serial)

    password = input("Enter password again: ")
    ctx = EncryptionKey(password)

    try:
        olivier2 = deserialize(User, serial, ctx)
    except InvalidToken:
        print("Invalid password!")
        return

    show("Deserialized", olivier2)

    assert olivier == olivier2


# This is for the regression tests we run on the examples with pytest
# Fernet uses a random component, so the output is not deterministic
main.do_not_test_output = True


if __name__ == "__main__":
    main(input)
