from collections.abc import AsyncGenerator

from use_cases.dashboard.load_dashboard_stats_usecase import LoadDashboardStatsUseCase
from use_cases.dashboard.stream_dashboard_stats_usecase import (
    StreamDashboardStatsUseCase,
)
from ui.widgets.dashboard.dashboard_view_model import DashboardViewModel


class EdDashboardPresenter:
    def __init__(
        self,
        load_dashboard_stats_usecase: LoadDashboardStatsUseCase,
        stream_dashboard_stats_usecase: StreamDashboardStatsUseCase,
    ) -> None:
        self.load_dashboard_stats_usecase = load_dashboard_stats_usecase
        self.stream_dashboard_stats_usecase = stream_dashboard_stats_usecase

    def get_dashboard_stats(self) -> DashboardViewModel:
        return self.load_dashboard_stats_usecase()

    def stream_dashboard_stats(self) -> AsyncGenerator[DashboardViewModel, None]:
        return self.stream_dashboard_stats_usecase()
