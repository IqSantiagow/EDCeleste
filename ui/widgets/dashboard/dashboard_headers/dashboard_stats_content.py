from textual import work
from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Rule
from textual.reactive import reactive

from ui.widgets.dashboard.dashboard_headers.widget_common_stat_label import (
    WidgetCommonStatLabel,
)
from ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository
from ui.widgets.dashboard.view_models.dashboard_stats_view_model import (
    DashboardStatsViewModel,
)


class DashboardStatsContent(HorizontalGroup):
    """Widget to display dashboard stats content."""

    state: reactive[DashboardStatsViewModel] = reactive(DashboardStatsViewModel.empty())

    def __init__(
        self,
        ed_dashboard_repository: EdDashboardRepository,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.ed_dashboard_repository = ed_dashboard_repository

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="dashboard-stats-content"):
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="SYS", stat_value="", id="stat-sys")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="SHIP", stat_value="", id="stat-ship")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="HULL", stat_value="", id="stat-hull")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="FUEL", stat_value="", id="stat-fuel")

    def on_mount(self) -> None:
        self.set_up_stream_worker()

    def watch_state(self, new_state: DashboardStatsViewModel) -> None:
        self.query_one("#stat-sys", WidgetCommonStatLabel).update_value(
            new_state.location
        )
        self.query_one("#stat-ship", WidgetCommonStatLabel).update_value(new_state.ship)
        self.query_one("#stat-fuel", WidgetCommonStatLabel).update_value(new_state.fuel)

    @work
    async def set_up_stream_worker(self) -> None:
        async for (
            dashboard_state
        ) in self.ed_dashboard_repository.stream_dashboard_stats():
            self.state = dashboard_state
