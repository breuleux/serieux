from dataclasses import dataclass
from typing import Callable

MISSING = object()


@dataclass(kw_only=True)
class Field:
    name: str
    type: type
    default: object = MISSING
    default_factory: Callable = MISSING

    argument_name: str | int = MISSING
    property_name: str = MISSING
    serialized_name: str = MISSING

    # Not implemented yet
    flatten: bool = False

    def __post_init__(self):
        if self.property_name is MISSING:
            self.property_name = self.name
        if self.argument_name is MISSING:
            self.argument_name = self.name
        if self.serialized_name is MISSING:
            self.serialized_name = self.name

    @property
    def required(self):
        return self.default is MISSING and self.default_factory is MISSING

    def extract(self, value):
        return getattr(value, self.property_name)

    def extract_codegen(self):
        return f"$$$.{self.property_name}"


@dataclass(kw_only=True)
class Model:
    original_type: type
    fields: list[Field]
    constructor: Callable
