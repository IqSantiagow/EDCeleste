from dataclasses import dataclass


@dataclass(slots=True)
class DashboardViewModel:
    location: str
    ship: str
    fuel: str

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, str]) -> "DashboardViewModel":
        return cls(
            location=snapshot.get("location", ""),
            ship=snapshot.get("ship", ""),
            fuel=snapshot.get("fuel", ""),
        )

    @classmethod
    def empty(cls) -> "DashboardViewModel":
        return cls(location="", ship="", fuel="")
