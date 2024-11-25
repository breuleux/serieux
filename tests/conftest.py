from io import StringIO

import pytest

from serieux.exc import ValidationExceptionGroup


@pytest.hookimpl()
def pytest_exception_interact(node, call, report):
    if call.excinfo.type == ValidationExceptionGroup:
        exc = call.excinfo.value
        io = StringIO()
        exc.display(file=io)
        entry = report.longrepr.reprtraceback.reprentries[-1]
        entry.style = "short"
        entry.lines = [io.getvalue()]
        report.longrepr.reprtraceback.reprentries = [entry]
