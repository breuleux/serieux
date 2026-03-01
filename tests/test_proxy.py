import copy
import math

from serieux.features.comment import CommentProxy
from serieux.proxy import LazyProxy

from .definitions import Point


def test_lazy_proxy():
    lazy_value = LazyProxy(lambda: 42)

    assert lazy_value
    assert lazy_value == 42
    assert str(lazy_value) == "42"
    assert repr(lazy_value) == "42"


def test_lazy_proxy_class_override():
    """__class__ returns _type when set."""
    lazy_with_type = LazyProxy(lambda: 42, type=Point)
    assert lazy_with_type.__class__ is Point


def test_lazy_setattr():
    pt = Point(1, 2)
    lpt = LazyProxy(lambda: pt)
    lpt.x = 333
    assert lpt.x == 333
    assert pt.x == 333


def test_lazy_arithmetic():
    lazy_a = LazyProxy(lambda: 10)
    lazy_b = LazyProxy(lambda: 5)
    lazy_c = LazyProxy(lambda: -3)

    assert lazy_a + lazy_b == 15
    assert lazy_a - lazy_b == 5
    assert lazy_a * lazy_b == 50
    assert lazy_a / lazy_b == 2.0
    assert lazy_a // lazy_b == 2
    assert lazy_a % lazy_b == 0
    assert lazy_a**lazy_b == 100000
    assert abs(lazy_c) == 3
    assert -lazy_c == 3
    assert +lazy_c == -3


def test_lazy_comparisons():
    lazy_value = LazyProxy(lambda: 42)
    assert lazy_value == 42
    assert lazy_value != 43
    assert lazy_value < 100
    assert lazy_value <= 42
    assert lazy_value > 0
    assert lazy_value >= 42


def test_lazy_hash():
    lazy_val = LazyProxy(lambda: 42)
    assert hash(lazy_val) == hash(42)
    assert lazy_val in {42}
    assert {lazy_val: "ok"}[42] == "ok"


def test_lazy_misc():
    laz = LazyProxy(lambda: 37.5)
    assert f"{laz:.3f}" == "37.500"


def test_lazy_list():
    lazy_list = LazyProxy(lambda: [1, 2, 3])

    assert len(lazy_list) == 3
    assert lazy_list[0] == 1
    assert list(lazy_list) == [1, 2, 3]
    assert 2 in lazy_list


# --- Container / sequence ---


def test_lazy_delitem():
    lst = [0, 1, 2, 3]
    lazy_lst = LazyProxy(lambda: lst)
    del lazy_lst[1]
    assert lst == [0, 2, 3]
    assert lazy_lst[0] == 0
    assert lazy_lst[1] == 2


def test_lazy_reversed():
    lazy_list = LazyProxy(lambda: [1, 2, 3])
    assert list(reversed(lazy_list)) == [3, 2, 1]


def test_lazy_index():
    lazy_int = LazyProxy(lambda: 4)
    lst = [10, 20, 30, 40, 50]
    assert lst[lazy_int] == 50


def test_lazy_setitem():
    lst = [0, 1, 2]
    lazy_lst = LazyProxy(lambda: lst)
    lazy_lst[1] = 99
    assert lazy_lst[1] == 99
    assert lst[1] == 99


# --- Context manager ---


def test_lazy_context_manager():
    class Ctx:
        def __enter__(self):
            self.entered = True
            return self

        def __exit__(self, *args):
            self.exited = True
            return False

    ctx = Ctx()
    lazy_ctx = LazyProxy(lambda: ctx)
    with lazy_ctx as c:
        assert c is ctx
        assert ctx.entered
    assert ctx.exited


# --- Attribute deletion ---


def test_lazy_delattr():
    pt = Point(1, 2)
    pt.extra = "temp"
    lpt = LazyProxy(lambda: pt)
    del lpt.extra
    assert not hasattr(pt, "extra")


def test_lazy_delattr_special_attribute():
    """Deleting __special_attributes__ goes through object.__delattr__."""
    proxy = CommentProxy(42, "note")
    assert proxy._ == "note"
    del proxy._
    assert not hasattr(proxy, "_")


# --- Numeric conversion ---


def test_lazy_numeric_conversion():
    lazy_int = LazyProxy(lambda: 42)
    lazy_float = LazyProxy(lambda: 3.7)
    lazy_complex = LazyProxy(lambda: 1 + 2j)

    assert int(lazy_int) == 42
    assert float(lazy_float) == 3.7
    assert complex(lazy_complex) == 1 + 2j


def test_lazy_round_trunc_floor_ceil():
    laz = LazyProxy(lambda: 3.7)
    assert round(laz) == 4
    assert round(laz, 1) == 3.7
    # Use math.* to invoke proxy's __trunc__/__floor__/__ceil__ (not _obj's via getattr)
    assert math.trunc(laz) == 3
    assert math.floor(laz) == 3
    assert math.ceil(laz) == 4


def test_lazy_bytes():
    lazy_bytes = LazyProxy(lambda: b"hello")
    assert bytes(lazy_bytes) == b"hello"


# --- Extended arithmetic ---


def test_lazy_divmod():
    lazy_a = LazyProxy(lambda: 17)
    lazy_b = LazyProxy(lambda: 5)
    assert divmod(lazy_a, lazy_b) == (3, 2)
    assert divmod(17, lazy_b) == (3, 2)


def test_lazy_matmul():
    # Use a simple class since list doesn't support @
    class Vec:
        def __init__(self, x, y):
            self.x, self.y = x, y

        def __matmul__(self, other):
            return self.x * other.x + self.y * other.y

        def __rmatmul__(self, other):
            return other.x * self.x + other.y * self.y

    class LeftOnly:
        """Returns NotImplemented so proxy.__rmatmul__ is used."""

        def __init__(self, x, y):
            self.x, self.y = x, y

        def __matmul__(self, other):
            return NotImplemented

    lazy_a = LazyProxy(lambda: Vec(1, 2))
    lazy_b = LazyProxy(lambda: Vec(3, 4))
    assert (lazy_a @ lazy_b) == 11  # 1*3 + 2*4
    assert (Vec(5, 6) @ lazy_b) == 39  # 5*3 + 6*4
    assert (LeftOnly(1, 2) @ lazy_b) == 11  # triggers __rmatmul__


# --- Bitwise ---


def test_lazy_bitwise():
    lazy_a = LazyProxy(lambda: 0b1010)  # 10
    lazy_b = LazyProxy(lambda: 0b0011)  # 3

    assert (lazy_a & lazy_b) == 2
    assert (lazy_a | lazy_b) == 11
    assert (lazy_a ^ lazy_b) == 9
    assert (lazy_a << 1) == 20
    assert (lazy_a >> 1) == 5
    assert (~lazy_a) == -11


def test_lazy_bitwise_reversed():
    lazy_val = LazyProxy(lambda: 4)
    assert (2 << lazy_val) == 32
    assert (64 >> lazy_val) == 4
    assert (0b1111 & lazy_val) == 4
    assert (0b0001 | lazy_val) == 5
    assert (0b0111 ^ lazy_val) == 3


# --- Copy ---


def test_lazy_copy():
    lst = [1, 2, 3]
    lazy_lst = LazyProxy(lambda: lst)
    copied = copy.copy(lazy_lst)
    assert copied == [1, 2, 3]
    assert copied is not lst


def test_lazy_deepcopy():
    nested = [[1, 2], [3, 4]]
    lazy_nested = LazyProxy(lambda: nested)
    deep_copied = copy.deepcopy(lazy_nested)
    assert deep_copied == [[1, 2], [3, 4]]
    assert deep_copied is not nested
    assert deep_copied[0] is not nested[0]


def test_lazy_deepcopy_explicit():
    """Explicit __deepcopy__ call to cover the memo parameter path."""
    lazy_val = LazyProxy(lambda: {"a": 1})
    memo = {}
    result = type(lazy_val).__deepcopy__(lazy_val, memo)
    assert result == {"a": 1}
    assert result is not lazy_val._obj


# --- Callable ---


def test_lazy_call():
    def greet(name):
        return f"Hello, {name}!"

    lazy_greet = LazyProxy(lambda: greet)
    assert lazy_greet("World") == "Hello, World!"


def test_lazy_proxy_deadlock():
    """Recursive evaluation during computation raises."""

    def recurse():
        return proxy._obj

    proxy = LazyProxy(recurse)
    try:
        _ = proxy._obj
    except Exception as e:
        assert "Deadlock" in str(e)
