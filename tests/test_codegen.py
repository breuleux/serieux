import inspect

import pytest

from serieux import Serieux, deserialize, serialize
from serieux.ctx import Context

from .definitions import Defaults, Point, World
from .test_serialize import Special

SEP = """
======
"""


def getcodes(fn, *sigs):
    sigs = [(sig if isinstance(sig, tuple) else (sig,)) for sig in sigs]
    codes = [inspect.getsource(fn.resolve(*sig)) for sig in sigs]
    return SEP.join(codes)


@pytest.mark.parametrize("cls", [Point, World, Defaults])
def test_serialize_codegen(cls, file_regression):
    code = getcodes(serialize, (type[cls], cls, Context))
    file_regression.check(code)


@pytest.mark.parametrize("cls", [Point, World, Defaults])
def test_deserialize_codegen(cls, file_regression):
    code = getcodes(deserialize, (type[cls], dict, Context))
    file_regression.check(code)


def test_special_serializer_codegen(file_regression):
    custom = (Serieux + Special)()
    code = getcodes(custom.serialize, (type[Point], Point, Context))
    file_regression.check(code)
