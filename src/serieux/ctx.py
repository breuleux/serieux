from dataclasses import replace

from ovld.medley import ChainAll, KeepLast, Medley


class Context(Medley, default_combiner=KeepLast):
    follow = ChainAll()


class EmptyContext(Context):
    pass


class AccessPath(Context):
    full_path: tuple = ()

    @property
    def access_path(self):
        return tuple(k for _, k in self.full_path)

    def follow(self, objt, obj, field):
        return replace(self, full_path=(*self.full_path, (obj, field)))


empty = EmptyContext()
