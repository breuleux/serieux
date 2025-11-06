from dataclasses import dataclass


@dataclass
class Citizen:
    name: str
    birthyear: int
    hometown: str


@dataclass
class Country:
    languages: list[str]
    capital: str
    population: int
    citizens: list[Citizen]


@dataclass
class World:
    countries: dict[str, Country]


canada = Country(
    languages=["English", "French"],
    capital="Ottawa",
    population=39_000_000,
    citizens=[
        Citizen(
            name="Olivier",
            birthyear=1985,
            hometown="Montreal",
        ),
        Citizen(
            name="Abraham",
            birthyear=2018,
            hometown="Shawinigan",
        ),
    ],
)


world = World(countries={"canada": canada})


big_world = World(
    countries={
        f"country_{i}": Country(
            languages=[f"Language_{i}_A", f"Language_{i}_B"],
            capital=f"Capital_{i}",
            population=1_000_000 + i * 50_000,
            citizens=[
                Citizen(
                    name=f"Citizen_{i}_{j}",
                    birthyear=1970 + (j % 50),
                    hometown=f"Hometown_{i}_{j}",
                )
                for j in range(100)
            ],
        )
        for i in range(100)
    }
)

roboland = Country(
    languages=[f"Robolang{i}" for i in range(10000)],
    capital="Robopolis",
    population=1000,
    citizens=[
        Citizen(
            f"Bobot{i}",
            birthyear=3000 + i,
            hometown=f"Bobotown{i}",
        )
        for i in range(1000)
    ],
)
