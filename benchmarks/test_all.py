from __future__ import annotations

import json
from pathlib import Path

import pytest

from serieux import IncludeFile, Serieux, serialize

from .matrix import Matrix

here = Path(__file__).parent
deserialize = (Serieux + IncludeFile)().deserialize


def bench(path):
    matrix = deserialize(Matrix, path)
    return pytest.mark.parametrize("case", matrix.generate_cases())


@bench(here / "matrix.yaml")
def test_serialize(case, benchmark):
    case.xfail_guard()
    data_ser = serialize(case.data)
    fn = case.adapter.deserializer_for_type(type(case.data))
    result = benchmark(fn, data_ser)
    assert result == case.data


@bench(here / "matrix-json.yaml")
def test_json(case, benchmark):
    case.xfail_guard()
    fn = case.adapter.json_for_type(type(case.data))
    result = benchmark(fn, case.data)
    assert json.loads(result) == serialize(type(case.data), case.data)


@bench(here / "matrix.yaml")
def test_deserialize(case, benchmark):
    case.xfail_guard()
    data_ser = serialize(case.data)
    fn = case.adapter.deserializer_for_type(type(case.data))
    result = benchmark(fn, data_ser)
    assert result == case.data
