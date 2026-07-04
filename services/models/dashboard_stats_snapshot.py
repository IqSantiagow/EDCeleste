from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DashboardStatsSnapshot:
    """Typed snapshot of the dashboard-relevant game state.

    Produced by the game-state service and translated into a UI view model by
    the dashboard use case. Immutable: it is a point-in-time read, not state.
    """

    location: str
    ship: str
    fuel: str
