from abc import ABC, abstractmethod


class Adapter(ABC):
    """Base class for all serialization/deserialization adapters."""

    @abstractmethod
    def serializer_for_type(self, t):
        """Return a serializer function for the given type."""
        pass

    @abstractmethod
    def json_for_type(self, t):
        """Return a JSON serializer function for the given type."""
        pass

    @abstractmethod
    def deserializer_for_type(self, t):
        """Return a deserializer function for the given type."""
        pass
