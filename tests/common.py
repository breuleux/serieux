from dataclasses import dataclass


@dataclass
class Citizen:
    name: str
    birthyear: int
    hometown: str


@dataclass
class Country:
    languages: list[str]
    capital: str
    population: int
    citizens: list[Citizen]


@dataclass
class World:
    countries: dict[str, Country]


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Point3D(Point):
    z: int
