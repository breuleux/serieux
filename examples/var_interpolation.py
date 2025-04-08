import re
from dataclasses import dataclass, field
from functools import partial

from ovld import Medley, call_next, ovld
from ovld.dependent import Regexp

from serieux import Serieux, deserialize
from serieux.ctx import AccessPath
from serieux.lazy import LazyProxy

##################
# Implementation #
##################


class Variables(AccessPath):
    refs: dict[tuple[str, ...], object] = field(default_factory=dict)


def evaluate(expr, ctx):
    current = tuple(k for _, k in ctx.access_path[:-1])
    while True:
        lcl = vars(ctx.refs[current])
        try:
            return eval(expr, lcl, lcl)
        except NameError:
            pass
        if not current:
            raise Exception(f"Failed to evaluate expression: {expr}")
        current = current[:-1]


@Serieux.extend
class VarInterpolation(Medley):
    @ovld(priority=1)
    def deserialize(self, typ: type[object], value: object, ctx: Variables):
        rval = call_next(typ, value, ctx)
        pth = tuple(k for _, k in ctx.access_path)
        ctx.refs[pth] = rval
        return rval

    @ovld(priority=3)
    def deserialize(self, typ: type[object], value: Regexp[r"^\$\{.+\}$"], ctx: Variables):
        expr = value.lstrip("${").rstrip("}")
        return LazyProxy(partial(evaluate, expr, ctx))

    @ovld(priority=2)
    def deserialize(self, typ: type[object], value: Regexp[r"\$\{.+\}"], ctx: Variables):
        def interpolate():
            def repl(match):
                return str(evaluate(match.group(1), ctx))

            return re.sub(r"\$\{(.+)\}", repl, value)

        return LazyProxy(interpolate)


#################
# Demonstration #
#################


@dataclass
class Philosopher:
    name: str
    school_of_thought: str
    birth_year: int


@dataclass
class DebatingSociety:
    founder: Philosopher
    rival_philosopher: Philosopher
    meeting_place: str
    year_established: int


def main():
    plato = {"name": "Plato", "school_of_thought": "Platonism", "birth_year": -428}

    aristotle = {
        "name": "Aristotle",
        "school_of_thought": "Team ${name}",
        "birth_year": -384,
    }

    academy_serialized = {
        "founder": plato,
        "rival_philosopher": aristotle,
        "meeting_place": "Athens",
        "year_established": "${founder.birth_year}",
    }

    academy = deserialize(DebatingSociety, academy_serialized, Variables())
    print("Deserialized:", academy)
    assert academy.year_established == -428
    assert academy.rival_philosopher.school_of_thought == "Team Aristotle"


if __name__ == "__main__":
    main()
