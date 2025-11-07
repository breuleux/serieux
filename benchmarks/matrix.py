from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

import pytest

from benchmarks.adapters.base import Adapter
from serieux.features.registered import Referenced
from serieux.features.tagset import TaggedSubclass


@dataclass
class Matrix:
    adapters: dict[str, TaggedSubclass[Adapter]]
    data: dict[str, Referenced[Any]]
    xfails: list[list[str]] = field(default_factory=list)

    def generate_cases(self):
        for (dn, d), (an, a) in itertools.product(self.data.items(), self.adapters.items()):
            yield Case(
                adapter=a,
                data=d,
                adapter_name=an,
                data_name=dn,
                xfail=[an, dn] in self.xfails,
            )


@dataclass
class Case:
    adapter: Adapter
    data: Any
    adapter_name: str
    data_name: str
    xfail: bool = False

    def __post_init__(self):
        self.__name__ = f"{self.data_name},{self.adapter_name}"

    def xfail_guard(self):
        if self.xfail:
            pytest.xfail("known failure for this data/interface combination")
