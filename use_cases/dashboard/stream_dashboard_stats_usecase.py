from typing import AsyncGenerator

from protocols.game_state_reader import GameStateReader
from ui.widgets.dashboard.view_models.dashboard_view_model import (
    DashboardStatsViewModel,
)


class StreamDashboardStatsUseCase:
    game_state_reader: GameStateReader

    def __init__(self, game_state_reader: GameStateReader) -> None:
        self.game_state_reader = game_state_reader

    async def __call__(self) -> AsyncGenerator[DashboardStatsViewModel, None]:
        async for snapshot in self.game_state_reader.stream_dashboard_stats():
            yield DashboardStatsViewModel.from_snapshot(snapshot)
