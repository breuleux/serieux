from dataclasses import dataclass, field
from random import (
    choice,
    expovariate as exp,  # noqa: F401
    normalvariate as normal,  # noqa: F401
    randint,  # noqa: F401
    random as rand,  # noqa: F401
    seed,
    uniform,  # noqa: F401
)

from ovld import Medley, recurse
from ovld.dependent import Regexp

from serieux import Serieux, deserialize
from serieux.ctx import AccessPath, Context

##################
# Implementation #
##################


@dataclass
class Tracker:
    length: int
    current: int = 0

    def advance(self):
        self.current = (self.current + 1) % self.length
        return self.current == 0


class Grid(AccessPath):
    trackers: dict[str, Tracker] = field(default_factory=dict)

    def get_choice(self, choices):
        if (acc := self.access_path) not in self.trackers:
            self.trackers[acc] = Tracker(len(choices))
        tracker = self.trackers[acc]
        assert tracker.length == len(choices)
        return choices[tracker.current]

    def advance(self):
        for tracker in self.trackers.values():
            if not tracker.advance():
                return True
        else:
            return False


@Serieux.extend
class Sampler(Medley):
    def deserialize(self, typ: type[object], obj: Regexp["^~"], ctx: Context):
        return eval(obj.lstrip("~"), globals())

    def deserialize(self, typ: type[object], obj: list, ctx: Context):
        return recurse(typ, choice(obj), ctx)

    def deserialize(self, typ: type[object], obj: list, ctx: Grid):
        return recurse(typ, ctx.get_choice(obj), ctx)


#################
# Demonstration #
#################


@dataclass
class Config:
    lr: float
    model: str
    dataset: str


def main():
    seed(1234)
    cfg = {
        "lr": "~exp()",
        "model": ["ConvNet", "AutoEncoder", "LLM"],
        "dataset": ["MNIST", "ImageNet", "CIFAR-10"],
    }
    g = Grid()
    while True:
        print(deserialize(Config, cfg, g))
        if not g.advance():
            break


if __name__ == "__main__":
    main()
