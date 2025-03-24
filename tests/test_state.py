from dataclasses import dataclass

from serieux.state import State, empty


@dataclass
class Filename(State):
    filename: str


@dataclass
class Depth(State):
    depth: int


def test_add_same_type():
    f1 = Filename("file1")
    f2 = Filename("file2")
    assert (f1 + f2).filename == "file2"
    assert type(f1 + f2) is Filename


def test_add_different_type():
    fd = Filename("file") + Depth(10)
    assert fd.filename == "file"
    assert fd.depth == 10
    assert isinstance(fd, Filename)
    assert isinstance(fd, Depth)


def test_subtract():
    f = Filename("file")
    d = Depth(10)
    fd = f + d
    assert fd.filename == "file"
    assert fd.depth == 10

    f2 = fd - Depth
    assert f2.filename == "file"
    assert isinstance(f2, Filename)
    assert not hasattr(f2, "depth")

    f3 = fd - Filename
    assert fd.depth == 10
    assert not hasattr(f3, "filename")

    f4 = fd - Filename - Depth
    assert not hasattr(f4, "filename")
    assert not hasattr(f4, "depth")


def test_change():
    f = Filename("file")
    d = Depth(10)
    fd = f + d
    assert fd.filename == "file"
    fd.filename = "wow"
    assert fd.filename == "wow"
    assert f.filename == "wow"


def test_empty_state():
    f = Filename("file")
    assert empty + f is f
