from textual import log, work
from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Rule
from textual.reactive import reactive
from dependency_injector.wiring import Provide, inject

from containers.main_container import Container
from ui.widgets.dashboard.dashboard_headers.widget_common_stat_label import (
    WidgetCommonStatLabel,
)
from ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository
from ui.widgets.dashboard.view_models.dashboard_stats_view_model import (
    DashboardStatsViewModel,
)
from ui.widgets.dashboard.view_models.llm_jrnl_healthcheck_view_model import (
    LlmJrnlHealthCheckViewModel,
)


class DashboardStatsContent(HorizontalGroup):
    """Widget to display dashboard stats content."""

    state: reactive[DashboardStatsViewModel] = reactive(DashboardStatsViewModel.empty())
    healthcheck_state: reactive[LlmJrnlHealthCheckViewModel] = reactive(
        LlmJrnlHealthCheckViewModel.empty()
    )

    @inject
    def __init__(
        self,
        ed_dashboard_repository: EdDashboardRepository = Provide[
            Container.ed_dashboard_repository
        ],
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
        with HorizontalGroup(id="dashboard-jrnl-llm-status"):
            yield WidgetCommonStatLabel(text="LLM", stat_value="OK", id="stat-llm")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="JRNL", stat_value="OK", id="stat-jrnl")

    def on_mount(self) -> None:
        self.set_up_stream_worker()
        self.set_up_healthcheck_stream_worker()

    def watch_state(self, new_state: DashboardStatsViewModel) -> None:
        self.query_one("#stat-sys", WidgetCommonStatLabel).update_value(
            new_state.location
        )
        self.query_one("#stat-ship", WidgetCommonStatLabel).update_value(new_state.ship)
        self.query_one("#stat-fuel", WidgetCommonStatLabel).update_value(new_state.fuel)

    def watch_healthcheck_state(self, new_state: LlmJrnlHealthCheckViewModel) -> None:
        self.query_one("#stat-llm", WidgetCommonStatLabel).update_value(
            "OK" if new_state.llm_healthcheck else "FAIL"
        )
        self.query_one("#stat-jrnl", WidgetCommonStatLabel).update_value(
            "OK" if new_state.journal_healthcheck else "FAIL"
        )

    @work
    async def set_up_stream_worker(self) -> None:
        async for (
            dashboard_state
        ) in self.ed_dashboard_repository.stream_dashboard_stats():
            self.state = dashboard_state

    @work
    async def set_up_healthcheck_stream_worker(self) -> None:
        async for (
            healthcheck_state
        ) in self.ed_dashboard_repository.stream_healthcheck():
            self.healthcheck_state = healthcheck_state
            log.info(f"Updated healthcheck state: {self.healthcheck_state}")
