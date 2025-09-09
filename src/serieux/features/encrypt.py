import base64
import json
from functools import cache
from hashlib import sha256
from typing import TYPE_CHECKING, Annotated, Any, Callable, TypeAlias

from ovld import Medley, call_next, ovld, recurse
from ovld.dependent import Regexp

from ..ctx import Context, Patch, Patcher
from ..instructions import Instruction, T
from ..priority import STD

try:
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover
    raise ImportError(
        "The 'cryptography' package is required for encryption features. "
        "Please install it with 'pip install cryptography'."
    )


#############
# Constants #
#############


if TYPE_CHECKING:
    Secret: TypeAlias = Annotated[T, None]
else:
    Secret = Instruction("Secret")


crypt_prefix = "~CRYPT~"


###########
# Context #
###########


class EncryptionKey(Context):
    password: str | Callable = None
    fernet_key: Fernet = None

    def __post_init__(self):
        if callable(self.password):
            self.password = cache(self.password)

    def get_encryption_key(self):
        if self.fernet_key is None:
            pw = self.password
            if callable(pw):
                pw = self.password()
            elif pw is None:
                raise Exception("No encryption password or key was provided")
            encoded = base64.b64encode(sha256(pw.encode()).digest())
            self.fernet_key = Fernet(encoded)

        return self.fernet_key

    def encrypt(self, value):
        ek = self.get_encryption_key()
        encrypted = ek.encrypt(json.dumps(value).encode("utf8")).decode("utf8")
        return f"{crypt_prefix}{encrypted}"

    def decrypt(self, encrypted: str):
        ek = self.get_encryption_key()
        return json.loads(ek.decrypt(encrypted.lstrip(crypt_prefix)))


##################
# Implementation #
##################

PRIO1 = STD.next()
PRIO2 = STD.next()


class Encrypt(Medley):
    @ovld(priority=PRIO2)
    def serialize(self, t: type[Any @ Secret], obj: object, ctx: EncryptionKey):
        result = call_next(Secret.strip(t), obj, ctx - EncryptionKey)
        return ctx.encrypt(result)

    @ovld(priority=PRIO2)
    def deserialize(
        self, t: type[Any @ Secret], obj: Regexp[rf"^{crypt_prefix}.*"], ctx: EncryptionKey
    ):
        obj = ctx.decrypt(obj)
        return call_next(Secret.strip(t), obj, ctx - EncryptionKey)

    @ovld(priority=PRIO1)
    def deserialize(self, t: type[Any @ Secret], obj: Any, ctx: EncryptionKey + Patcher):
        def crypt():
            return ctx.encrypt(obj)

        ctx.declare_patch(Patch(crypt, description="Encrypt value"))
        return recurse(Secret.strip(t), obj, ctx)
