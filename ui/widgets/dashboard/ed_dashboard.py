from textual import log, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label, Rule
from textual.reactive import reactive
from dependency_injector.wiring import Provide, inject


from containers.main_container import Container
from ui.widgets.dashboard.comms.widget_comms_col import WidgetCommsCol
from ui.widgets.dashboard.dashboard_headers.widget_common_stat_label import (
    WidgetCommonStatLabel,
)
from ui.widgets.dashboard.dashboard_view_model import DashboardViewModel
from ui.widgets.dashboard.ed_dashboard_presenter import EdDashboardPresenter
from ui.widgets.dashboard.ship_log.widget_ship_log_col import WidgetShipLogCol


class EdDashboard(Widget):
    state: reactive[DashboardViewModel] = reactive(DashboardViewModel.empty())

    @inject
    def __init__(
        self,
        ed_dashboard_presenter: EdDashboardPresenter = Provide[
            Container.ed_dashboard_presenter
        ],
    ) -> None:
        super().__init__()
        self.ed_dashboard_presenter = ed_dashboard_presenter

    def watch_state(self, new_state: DashboardViewModel) -> None:
        self.query_one("#stat-sys", WidgetCommonStatLabel).update_value(
            new_state.location
        )
        self.query_one("#stat-ship", WidgetCommonStatLabel).update_value(new_state.ship)
        self.query_one("#stat-fuel", WidgetCommonStatLabel).update_value(new_state.fuel)

    def on_mount(self) -> None:
        self.state = self.ed_dashboard_presenter.get_dashboard_stats()
        log.info(f"Initial dashboard state: {self.state}")
        self.set_up_stream_worker()

    def compose(self) -> ComposeResult:
        with Horizontal(id="dashboard-main"):
            with Horizontal(id="dashboard-header"):
                yield Label(content="EDCeleste Dashboard", id="dashboard-title")
                yield Rule(orientation="vertical")
                yield WidgetCommonStatLabel(text="SYS", stat_value="", id="stat-sys")
                yield Rule(orientation="vertical")
                yield WidgetCommonStatLabel(text="SHIP", stat_value="", id="stat-ship")
                yield Rule(orientation="vertical")
                yield WidgetCommonStatLabel(text="HULL", stat_value="", id="stat-hull")
                yield Rule(orientation="vertical")
                yield WidgetCommonStatLabel(text="FUEL", stat_value="", id="stat-fuel")
            with Horizontal(id="dashboard-status"):
                yield WidgetCommonStatLabel(text="LLM", stat_value="OK")
                yield Rule(orientation="vertical")
                yield WidgetCommonStatLabel(text="JRNL", stat_value="OK")
        with Horizontal(id="dashboard-body"):
            yield WidgetCommsCol()
            yield WidgetShipLogCol()

    @work(exclusive=True)
    async def set_up_stream_worker(self) -> None:
        async for (
            dashboard_state
        ) in self.ed_dashboard_presenter.stream_dashboard_stats():
            self.state = dashboard_state
            log.info(f"Updated dashboard state: {self.state}")
