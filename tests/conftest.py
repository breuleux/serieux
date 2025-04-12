import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pytest

from serieux.exc import ValidationError, ValidationExceptionGroup

datapath = Path(__file__).parent / "data"


@pytest.hookimpl()
def pytest_exception_interact(node, call, report):
    if call.excinfo.type == ValidationExceptionGroup or call.excinfo.type == ValidationError:
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
    def check(message="", exc_type=(ValidationError, ValidationExceptionGroup)):
        with pytest.raises(exc_type, match=message) as exc:
            yield

        exc.value.display(file=sys.stderr)
        cap = capsys.readouterr()
        out = cap.out.replace(str(datapath.parent), "REDACTED")
        err = cap.err.replace(str(datapath.parent), "REDACTED")
        file_regression.check("\n".join([out, "=" * 80, err]))

    yield check
