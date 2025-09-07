from typing import Annotated, Literal

from serieux import deserialize, schema, serialize
from serieux.instructions import Instruction, inherit, pushdown, strip

from .common import one_test_per_assert
from .features.test_usermeth import RGB

Apple = Instruction("Apple", annotation_priority=1)
Banana = Instruction("Banana", annotation_priority=2)
Carrot = Instruction("Carrot", annotation_priority=3)
Dog = Instruction("Dog", annotation_priority=4, inherit=False)
Useless = Instruction("Useless", annotation_priority=1, inherit=True)


@one_test_per_assert
def test_typetag_strip():
    assert strip(Apple[int], Apple) is int
    assert strip(Apple[Banana[int]], Apple) is Banana[int]
    assert strip(Banana[Apple[int]], Banana) is Apple[int]
    assert strip(Banana[int], Banana) is int
    assert strip(int, Apple) is int


@one_test_per_assert
def test_pushdown():
    assert pushdown(int) is int
    assert pushdown(Apple[int]) is int
    assert pushdown(Apple[list[int]]) == list[Apple[int]]
    assert pushdown(Apple[Banana[list[int]]]) == list[Apple[Banana[int]]]
    assert pushdown(Apple[int | str]) == Apple[int] | Apple[str]


def test_pushdown_literal():
    assert pushdown(Apple[Literal[1, 2]]) == Literal[1, 2]


@one_test_per_assert
def test_pushdown_no_inherit():
    # Dog is a tag that is not inherited when pushing down
    assert pushdown(Dog[list[int]]) == list[int]
    assert pushdown(Dog[Apple[list[int]]]) == list[Apple[int]]


def test_ser_deser_ignores_them():
    assert serialize(Useless[RGB], RGB(1, 2, 3)) == "#010203"
    assert deserialize(Useless[RGB], "#010203") == RGB(1, 2, 3)
    s1 = schema(Useless[RGB]).json()
    s2 = schema(RGB).json()
    assert s1 == s2


@one_test_per_assert
def test_inherit():
    assert inherit(int @ Banana @ Apple, float) == float @ Banana @ Apple
    assert inherit(int @ Apple @ Dog, float) == float @ Apple
    assert inherit(int @ Dog, float) is float
    assert inherit(int @ Banana @ Dog @ Apple, float) == float @ Banana @ Apple
    assert inherit(int, float) is float
    assert inherit(Annotated[int, "unrelated"], float) is float
    assert inherit(Annotated[int, Apple, "unrelated"], float) == float @ Apple
