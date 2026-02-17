from serieux import Serieux
from serieux.features.fromfile import IncludeFile
from serieux.features.interpol import Environment, Interpolation
from tests.definitions import Character

deserialize = (Serieux + IncludeFile + Interpolation)().deserialize


def test_interpol_include(datapath):
    """Test interpolation in $include, e.g. $include: ${env:XYZ}"""
    ca = deserialize(
        Character,
        datapath / "character-dyn.yaml",
        Environment(environ={"BACKSTORY": "jimbo.txt"}),
    )
    cb = deserialize(
        Character,
        datapath / "character-dyn.yaml",
        Environment(environ={"BACKSTORY": "jumbo.txt"}),
    )
    assert ca.backstory != cb.backstory
    assert ca.backstory == (datapath / "jimbo.txt").read_text()
    assert cb.backstory == (datapath / "jumbo.txt").read_text()
