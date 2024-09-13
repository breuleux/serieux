from __future__ import annotations

from dataclasses import dataclass
from numbers import Number


@dataclass
class Tree:
    left: Tree | Number
    right: Tree | Number
