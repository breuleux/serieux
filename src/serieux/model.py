from dataclasses import dataclass
from typing import Callable


@dataclass
class Field:
    name: str = None
    type: object = object


@dataclass
class Model:
    builder: Callable


@dataclass
class StructuredModel(Model):
    fields: dict[str, Field]

    def __post_init__(self):
        for k, f in self.fields.items():
            assert f.name is None or f.name == k
            f.name = k


@dataclass
class ListModel(Model):
    element_type: type
    extractor: Callable


@dataclass
class MappingModel(Model):
    key_type: type
    element_type: type
    extractor: Callable


@dataclass
class Partial:
    model: Model
    args: list
    kwargs: dict
