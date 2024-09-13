from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Tree[T]:
    left: Tree[T] | T
    right: Tree[T] | T
