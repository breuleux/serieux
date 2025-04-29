from __future__ import annotations

from dataclasses import dataclass

from .base import Line


@dataclass
class DrawingLine(Line):
    thickness: int
