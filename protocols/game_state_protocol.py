from typing import AsyncGenerator, Protocol

from services.models.dashboard_stats_snapshot import DashboardStatsSnapshot
from services.models.game_events import GameEvent


class GameStateProtocol(Protocol):
    def get_dashboard_stats(self) -> DashboardStatsSnapshot: ...

    def stream_dashboard_stats(
        self,
    ) -> AsyncGenerator[DashboardStatsSnapshot, None]: ...

    def stream_journal_events(self) -> AsyncGenerator[GameEvent, None]: ...

    def get_game_state_projection(self) -> str: ...
