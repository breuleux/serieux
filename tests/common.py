import ast
import inspect
from ast import NodeTransformer
from dataclasses import dataclass
from textwrap import dedent

from _pytest.assertion.rewrite import AssertionRewriter


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


class AssertTransformer(NodeTransformer):
    def visit_FunctionDef(self, node):
        newfns = []
        for i, stmt in enumerate(node.body):
            if not isinstance(stmt, ast.Assert):
                raise Exception("@one_test_per_assert requires all statements to be asserts")
            else:
                newfns.append(
                    ast.FunctionDef(
                        name=f"{node.name}_assert{i + 1}",
                        args=node.args,
                        body=[stmt],
                        decorator_list=node.decorator_list,
                        returns=node.returns,
                    )
                )
        return ast.Module(body=newfns, type_ignores=[])


def one_test_per_assert(fn):
    src = dedent(inspect.getsource(fn))
    filename = inspect.getsourcefile(fn)
    tree = ast.parse(src, filename)
    tree = tree.body[0]
    assert isinstance(tree, ast.FunctionDef)
    tree.decorator_list = []
    new_tree = AssertTransformer().visit(tree)
    ast.fix_missing_locations(new_tree)
    _, lineno = inspect.getsourcelines(fn)
    ast.increment_lineno(new_tree, lineno - 1)
    # Use pytest's assertion rewriter for nicer error messages
    AssertionRewriter(filename, None, None).run(new_tree)
    new_fn = compile(new_tree, filename, "exec")
    glb = fn.__globals__
    exec(new_fn, glb, glb)
    return None
