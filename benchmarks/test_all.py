from __future__ import annotations

import itertools
import json

import pytest

from serieux import serialize

from .adapters.adaptix import AdaptixAdapter
from .adapters.apischema import ApischemaAdapter
from .adapters.marshmallow import MarshmallowAdapter
from .adapters.mashumaro import MashumaroAdapter
from .adapters.pydantic import PydanticAdapter
from .adapters.serde import SerdeAdapter
from .adapters.serieux import SerieuxAdapter
from .data.point import point
from .data.tree import tree
from .data.world import big_world, roboland, world

adaptix = AdaptixAdapter()
adaptix.__name__ = "adaptix"
apischema = ApischemaAdapter()
apischema.__name__ = "apischema"
marshmallow = MarshmallowAdapter()
marshmallow.__name__ = "marshmallow"
mashumaro = MashumaroAdapter()
mashumaro.__name__ = "mashumaro"
pydantic = PydanticAdapter()
pydantic.__name__ = "pydantic"
serde = SerdeAdapter()
serde.__name__ = "serde"
serieux = SerieuxAdapter()
serieux.__name__ = "serieux"


id_to_thing = {id(v): k for k, v in globals().items()}


def bench(interfaces, data):
    cases = list(itertools.product(data, interfaces))
    return pytest.mark.parametrize(
        "data,interface",
        cases,
        ids=[f"{id_to_thing[id(d)]},{id_to_thing[id(i)]}" for d, i in cases],
    )


@bench(
    interfaces=[
        apischema,
        marshmallow,
        pydantic,
        adaptix,
        mashumaro,
        serieux,
        serde,
    ],
    data=[point, world, roboland, tree, big_world],
)
def test_serialize(interface, data, benchmark):
    fn = interface.serializer_for_type(type(data))
    result = benchmark(fn, data)
    assert result == serialize(type(data), data)


@bench(
    interfaces=[
        apischema,
        marshmallow,
        pydantic,
        adaptix,
        mashumaro,
        serieux,
        serde,
    ],
    data=[roboland],
)
def test_json(interface, data, benchmark):
    fn = interface.json_for_type(type(data))
    result = benchmark(fn, data)
    assert json.loads(result) == serialize(type(data), data)


@bench(
    interfaces=[
        apischema,
        marshmallow,
        pydantic,
        adaptix,
        mashumaro,
        serieux,
        serde,
    ],
    data=[point, world, roboland, tree, big_world],
)
def test_deserialize(interface, data, benchmark):
    data_ser = serialize(data)
    fn = interface.deserializer_for_type(type(data))
    result = benchmark(fn, data_ser)
    assert result == data
