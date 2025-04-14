from serieux import Serieux
from serieux.ctx import Context
from serieux.features.dotted import DottedNotation, unflatten
from tests.common import one_test_per_assert
from tests.definitions import Job, Worker

deserialize = (Serieux + DottedNotation)().deserialize


def test_unflatten():
    assert unflatten({"x.a": 1, "x.b": 2, "y": 3}) == {"x": {"a": 1, "b": 2}, "y": 3}


def test_unflatten_deep():
    assert unflatten({"a.b.c.d.e": 8}) == {"a": {"b": {"c": {"d": {"e": 8}}}}}


@one_test_per_assert
def test_unflatten_merge():
    assert unflatten({"x": {"a": 1}, "x.b": 2, "y": 3}) == {"x": {"a": 1, "b": 2}, "y": 3}
    assert unflatten({"x.b": 2, "y": 3, "x": {"a": 1}}) == {"x": {"a": 1, "b": 2}, "y": 3}
    assert unflatten({"a.b.c": {"z": 99}, "a.b.c.d.e": 8}) == {
        "a": {"b": {"c": {"z": 99, "d": {"e": 8}}}}
    }


def test_unflatten_ordering():
    d1 = {"b": 1, "a": 2, "r": 3, "n": 4}
    d2 = unflatten(d1)
    assert list(d2) == list("barn")

    d1 = {"b": 1, "a.x": 2, "r": 3, "n": 4}
    d2 = unflatten(d1)
    assert list(d2) == list("brna")

    d1 = {"b": 1, "a": {"y": 7}, "a.x": 2, "r": 3, "n": 4}
    d2 = unflatten(d1)
    assert list(d2) == list("barn")


def test_deserialize():
    data = {"name": "John Doe", "job.title": "Software Engineer", "job.yearly_pay": 80000.0}
    assert deserialize(Worker, data, Context()) == Worker(
        name="John Doe", job=Job(title="Software Engineer", yearly_pay=80000.0)
    )
