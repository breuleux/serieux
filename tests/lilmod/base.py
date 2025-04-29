from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Line:
    p1: Point
    p2: Point
