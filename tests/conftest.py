from io import StringIO

import pytest

from serieux.exc import ValidationError, ValidationExceptionGroup


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
