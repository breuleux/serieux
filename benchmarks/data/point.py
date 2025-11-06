from dataclasses import dataclass


@dataclass
class Point:
    x: int
    y: int


point = Point(x=17, y=83)
