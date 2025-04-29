from __future__ import annotations

from dataclasses import dataclass

from .definitions import Point


@dataclass
class Tree[T]:
    left: Tree[T] | T
    right: Tree[T] | T


type ListTreeP = list[Point | ListTreeP]


@dataclass
class LTHolder:
    lt: ListTreeP
