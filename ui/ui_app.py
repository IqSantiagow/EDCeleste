import logging
import threading

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.widgets import Footer, Label

from services.journal_watcher_service import JournalWatcherService
from ui.themes.themes import amber_theme
from ui.widgets.app_header import AppHeader
from ui.widgets.dashboard.comms.widget_comms_col import WidgetCommsCol
from ui.widgets.dashboard.comms.widget_comms_input import WidgetCommsInput
from ui.widgets.dashboard.dashboard_headers.dashboard_stats_content import (
    DashboardStatsContent,
)
from ui.widgets.dashboard.ed_dashboard_presenter import EdDashboardPresenter
from ui.widgets.dashboard.ship_log.widget_ship_log_col import WidgetShipLogCol
from ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)
from containers.main_container import Container
from dependency_injector.wiring import inject, Provide

logger = logging.getLogger(__name__)


class UIApp(App):
    CSS_PATH = "css.tcss"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    @inject
    def __init__(
        self,
        journal_watcher_service: JournalWatcherService = Provide[
            Container.journal_watcher_service_stub
        ],
        ed_dashboard_presenter: EdDashboardPresenter = Provide[
            Container.ed_dashboard_presenter
        ],
    ) -> None:
        super().__init__()
        self.journal_watcher_service = journal_watcher_service
        self.ed_dashboard_presenter = ed_dashboard_presenter

    def on_mount(self) -> None:
        self.register_theme(amber_theme)
        self.theme = "amber"
        self.watcher_thread = threading.Thread(
            target=self.journal_watcher_service.start_watcher_service,
            daemon=True,
        )
        self.watcher_thread.start()
        logger.info(
            "UIApp mounted. JournalWatcherService started in a separate thread."
        )

    def on_unmount(self) -> None:
        logger.info("UIApp unmounted. Stopping JournalWatcherService.")
        self.journal_watcher_service.stop_watcher_service()

    def compose(self) -> ComposeResult:
        with Grid(id="app-container"):
            yield AppHeader(content=DashboardStatsContent())
            yield Label(id="comms-title", classes="shady", content="COMMS")
            yield Label(id="ship-log-title", classes="shady", content="SHIP LOG")
            yield WidgetCommsCol(
                ed_dashboard_presenter=self.ed_dashboard_presenter, id="comms-col"
            )
            yield WidgetShipLogCol(
                ed_dashboard_presenter=self.ed_dashboard_presenter, id="ship-log-col"
            )
            yield WidgetCommsInput(
                ed_dashboard_presenter=self.ed_dashboard_presenter, id="input-row"
            )
            yield Footer(id="app-footer")

    @on(WidgetCommsInput.UserCommandSubmitted)
    def handle_user_command_submitted(
        self, event: WidgetCommsInput.UserCommandSubmitted
    ) -> None:
        logger.debug("User command submitted: %s", event.command)
        self.query_one(
            "#comms-col", WidgetCommsCol
        ).response_state = CommsMessageViewModel.from_user_message(event.command)
