from ovld import Medley


class Context(Medley):
    pass


class EmptyContext(Context):
    def __add__(self, other):
        return other


empty = EmptyContext()
