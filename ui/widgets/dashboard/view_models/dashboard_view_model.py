from dataclasses import dataclass


@dataclass(slots=True)
class DashboardStatsViewModel:
    location: str
    ship: str
    fuel: str

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, str]) -> "DashboardStatsViewModel":
        return cls(
            location=snapshot.get("location", ""),
            ship=snapshot.get("ship", ""),
            fuel=snapshot.get("fuel", ""),
        )

    @classmethod
    def empty(cls) -> "DashboardStatsViewModel":
        return cls(location="", ship="", fuel="")
