class PriorityLevel(tuple):
    def __new__(cls, *elements):
        obj = super().__new__(cls, elements)
        obj.current = 0
        return obj

    def next(self):
        self.current += 1
        return PriorityLevel(*self, self.current)

    def __call__(self, *elems):
        return PriorityLevel(*self, *elems)


class NamedInteger(int):
    def __new__(cls, value, name):
        obj = super().__new__(cls, value)
        obj._name = name
        return obj

    def __str__(self):
        return self._name

    __repr__ = __str__


MAX = PriorityLevel(NamedInteger(100, "MAX"))
HI9 = PriorityLevel(NamedInteger(9, "HI9"))
HI8 = PriorityLevel(NamedInteger(8, "HI8"))
HI7 = PriorityLevel(NamedInteger(7, "HI7"))
HI6 = PriorityLevel(NamedInteger(6, "HI6"))
HI5 = PriorityLevel(NamedInteger(5, "HI5"))
HI4 = PriorityLevel(NamedInteger(4, "HI4"))
HI3 = PriorityLevel(NamedInteger(3, "HI3"))
HI2 = PriorityLevel(NamedInteger(2, "HI2"))
HIGH = HI1 = PriorityLevel(NamedInteger(1, "HI1"))
DEFAULT = PriorityLevel(NamedInteger(0, "DEFAULT"))
STD5 = PriorityLevel(NamedInteger(-1, "STD5"))
STD4 = PriorityLevel(NamedInteger(-2, "STD4"))
STD3 = PriorityLevel(NamedInteger(-3, "STD3"))
STD2 = PriorityLevel(NamedInteger(-4, "STD2"))
STD = STD1 = PriorityLevel(NamedInteger(-5, "STD1"))
LOW = LO1 = PriorityLevel(NamedInteger(-11, "LO1"))
LO2 = PriorityLevel(NamedInteger(-12, "LO2"))
LO3 = PriorityLevel(NamedInteger(-13, "LO3"))
LO4 = PriorityLevel(NamedInteger(-14, "LO4"))
LO5 = PriorityLevel(NamedInteger(-15, "LO5"))
MIN = PriorityLevel(NamedInteger(-100, "MIN"))
