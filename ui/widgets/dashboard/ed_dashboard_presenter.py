from collections.abc import AsyncGenerator

from ui.widgets.dashboard.view_models.journal_log_view_model import JournalLogViewModel
from use_cases.dashboard.stream_dashboard_stats_usecase import (
    StreamDashboardStatsUseCase,
)
from ui.widgets.dashboard.view_models.dashboard_view_model import DashboardStatsViewModel
from use_cases.dashboard.stream_journal_events_usecase import StreamJournalEventsUseCase


class EdDashboardPresenter:
    def __init__(
        self,
        stream_dashboard_stats_usecase: StreamDashboardStatsUseCase,
        stream_journal_events_usecase: StreamJournalEventsUseCase
    ) -> None:
        self.stream_dashboard_stats_usecase = stream_dashboard_stats_usecase
        self.stream_journal_events_usecase = stream_journal_events_usecase

    def stream_dashboard_stats(self) -> AsyncGenerator[DashboardStatsViewModel, None]:
        return self.stream_dashboard_stats_usecase()

    def stream_journal_events(self) -> AsyncGenerator[JournalLogViewModel, None]:
        return self.stream_journal_events_usecase()
