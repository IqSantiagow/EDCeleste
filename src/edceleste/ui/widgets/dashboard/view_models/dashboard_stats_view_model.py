from dataclasses import dataclass

from edceleste.services.models.dashboard_stats_snapshot import DashboardStatsSnapshot


@dataclass(slots=True)
class DashboardStatsViewModel:
    location: str
    ship: str
    fuel: str

    @classmethod
    def from_snapshot(
        cls, snapshot: DashboardStatsSnapshot
    ) -> "DashboardStatsViewModel":
        return cls(
            location=snapshot.location,
            ship=snapshot.ship,
            fuel=snapshot.fuel,
        )

    @classmethod
    def empty(cls) -> "DashboardStatsViewModel":
        return cls(location="", ship="", fuel="")
