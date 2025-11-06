from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Tree:
    left: Tree | int
    right: Tree | int


tree = Tree(1, Tree(Tree(2, 3), Tree(4, Tree(5, Tree(6, Tree(7, Tree(8, 9)))))))
