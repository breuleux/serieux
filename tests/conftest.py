import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pytest

from serieux import Serieux
from serieux.exc import SerieuxError

datapath = Path(__file__).parent / "data"


@pytest.hookimpl()
def pytest_exception_interact(node, call, report):
    if issubclass(call.excinfo.type, SerieuxError):
        exc = call.excinfo.value
        io = StringIO()
        exc.display(file=io)
        entry = report.longrepr.reprtraceback.reprentries[-1]
        entry.style = "short"
        content = io.getvalue()
        entry.lines = [content] + [""] * content.count("\n")
        report.longrepr.reprtraceback.reprentries = [entry]


@pytest.fixture
def check_error_display(capsys, file_regression):
    @contextmanager
    def check(message=None, exc_type=SerieuxError):
        with pytest.raises(exc_type, match=message) as exc:
            yield

        exc.value.display(file=sys.stderr)
        cap = capsys.readouterr()
        out = cap.out.replace(str(datapath.parent), "REDACTED")
        err = cap.err.replace(str(datapath.parent), "REDACTED")
        file_regression.check("\n".join([out, "=" * 80, err]))

    yield check


@pytest.fixture
def fresh_serieux(monkeypatch):
    """Fixture that monkeypatches serieux module components for testing."""

    class NewSerieux(Serieux):
        pass

    new_serieux = NewSerieux()

    monkeypatch.setattr("serieux.serieux", new_serieux)
    monkeypatch.setattr("serieux.Serieux", NewSerieux)
    monkeypatch.setattr("serieux.deserialize", new_serieux.deserialize)
    monkeypatch.setattr("serieux.serialize", new_serieux.serialize)
    return new_serieux
