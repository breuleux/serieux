import importlib
from pathlib import Path

import pytest
from ovld import Medley

from serieux import Serieux

examples = Path(__file__).parent / "../examples"


example_files = [f for f in examples.glob("**/*.py") if not f.name.startswith("_")]


@pytest.fixture
def fresh_serieux(monkeypatch):
    """Fixture that monkeypatches serieux module components for testing."""

    class Empty(Medley):
        pass

    NewSerieux = Serieux + Empty
    new_serieux = NewSerieux()

    monkeypatch.setattr("serieux.serieux", new_serieux)
    monkeypatch.setattr("serieux.Serieux", NewSerieux)
    monkeypatch.setattr("serieux.deserialize", new_serieux.deserialize)
    monkeypatch.setattr("serieux.serialize", new_serieux.serialize)


@pytest.mark.parametrize("file", example_files, ids=lambda f: f.stem)
def test_example(file, file_regression, capsys, fresh_serieux):
    module_name = file.stem
    spec = importlib.util.spec_from_file_location(module_name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()
    if not getattr(module.main, "do_not_test_output", False):
        captured = capsys.readouterr()
        file_regression.check(captured.out)
