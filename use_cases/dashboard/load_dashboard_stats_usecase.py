from protocols.game_state_reader import GameStateReader
from ui.widgets.dashboard.dashboard_view_model import DashboardViewModel


class LoadDashboardStatsUseCase:
    game_state_reader: GameStateReader

    def __init__(self, game_state_reader: GameStateReader) -> None:
        self.game_state_reader = game_state_reader

    def __call__(self):
        return DashboardViewModel.from_snapshot(
            self.game_state_reader.get_dashboard_stats()
        )
