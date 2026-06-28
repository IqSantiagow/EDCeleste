from typing import AsyncGenerator

from protocols.game_state_reader import GameStateReader
from ui.widgets.dashboard.dashboard_view_model import DashboardViewModel


class StreamDashboardStatsUseCase:
    game_state_reader: GameStateReader

    def __init__(self, game_state_reader: GameStateReader) -> None:
        self.game_state_reader = game_state_reader

    async def __call__(self) -> AsyncGenerator[DashboardViewModel, None]:
        async for snapshot in self.game_state_reader.stream_dashboard_stats():
            yield DashboardViewModel.from_snapshot(snapshot)
