from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from numbers import Number


@dataclass
class Tree:
    left: Tree | Number
    right: Tree | Number


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


class Color(str, Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class Level(Enum):
    HI = 2
    MED = 1
    LO = 0


@dataclass
class Pig:
    # How pink the pig is
    pinkness: float

    weight: float
    """Weight of the pig, in kilograms"""

    # Is the pig...
    # truly...
    beautiful: bool = True  # ...beautiful?


@dataclass
class Defaults:
    name: str
    aliases: list[str] = field(default_factory=list)
    cool: bool = field(default=False, kw_only=True)


@dataclass
class Player:
    first: str
    last: str
    batting: float


@dataclass
class Team:
    name: str
    players: list[Player]


@dataclass
class Job:
    # Name of the job
    title: str
    # How much it pays, in dollars
    yearly_pay: float


@dataclass
class Worker:
    name: str
    job: Job = None


DID = dict[str, "int | DID"]


@dataclass
class DIDHolder:
    did: DID


ListTree = list["Point | ListTree"]


@dataclass
class LTHolder:
    lt: ListTree


class DotDict(dict):
    def __getattr__(self, attr):
        return self[attr]
