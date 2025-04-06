from dataclasses import replace

from ovld.medley import ChainAll, Medley


class Context(Medley):
    follow = ChainAll()


class EmptyContext(Context):
    def __add__(self, other):
        return other


class AccessPath(Context):
    access_path: tuple = ()

    def follow(self, objt, obj, field):
        return replace(self, access_path=(*self.access_path, (obj, field)))


empty = EmptyContext()
