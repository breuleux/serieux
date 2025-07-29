from serieux.features.proxy import CommentProxy, LazyProxy


def test_lazy_proxy():
    lazy_value = LazyProxy(lambda: 42)

    assert lazy_value
    assert lazy_value == 42
    assert str(lazy_value) == "42"
    assert repr(lazy_value) == "42"


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


def test_lazy_list():
    lazy_list = LazyProxy(lambda: [1, 2, 3])

    assert len(lazy_list) == 3
    assert lazy_list[0] == 1
    assert list(lazy_list) == [1, 2, 3]
    assert 2 in lazy_list


def test_commented_proxy():
    obj = [1, 2, 3]
    comment = "This is a comment"
    proxy = CommentProxy(obj, comment)

    # The proxy should behave like the original object
    assert proxy[0] == 1
    assert list(proxy) == [1, 2, 3]
    assert 2 in proxy
    assert str(proxy) == str(obj)
    assert repr(proxy) == repr(obj)

    # The comment should be accessible via the "_" attribute
    assert proxy._ == comment

    # The underlying object should be accessible via _obj
    assert proxy._obj is obj
