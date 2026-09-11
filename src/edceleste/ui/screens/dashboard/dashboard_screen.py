import logging
from textual.screen import Screen
from textual.widgets import Footer
from textual.containers import Grid
from textual.widgets import Label
from textual.app import ComposeResult
from textual import on, work
from edceleste.services.models.llm_status import LLMStatus
from edceleste.ui.screens.app.widgets.app_header import AppHeader
from edceleste.ui.screens.dashboard.widgets.comms.widget_comms_col import WidgetCommsCol
from edceleste.ui.screens.dashboard.widgets.comms.widget_comms_input import (
    WidgetCommsInput,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_col import (
    WidgetShipLogCol,
)
from edceleste.ui.screens.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)

logger = logging.getLogger(__name__)


class DashboardScreen(Screen):
    BINDINGS = [
        ("ctrl+r", "app.push_settings", "Settings"),
    ]

    def __init__(
        self,
        app_header_repository,
        dashboard_repository,
        settings_repository,
        journal_watcher_service,
        **kwargs,
    ):
        self.app_header_repository = app_header_repository
        self.dashboard_repository = dashboard_repository
        self.settings_repository = settings_repository
        self.journal_watcher_service = journal_watcher_service

        super().__init__(**kwargs)

    def on_mount(self) -> None:
        self.journal_watcher_service.start_watcher_service()
        self.__load_keybinds()
        self.set_up_llm_stream_worker()

    def compose(self) -> ComposeResult:
        with Grid(id="app-container", classes="screen-grid"):
            yield AppHeader(app_header_repository=self.app_header_repository)
            yield Label(id="comms-title", classes="header-title", content="COMMS")
            yield Label(id="ship-log-title", classes="header-title", content="SHIP LOG")
            yield WidgetCommsCol(id="comms-col")
            yield WidgetShipLogCol(
                ed_dashboard_repository=self.dashboard_repository, id="ship-log-col"
            )
            yield WidgetCommsInput(
                ed_dashboard_repository=self.dashboard_repository, id="input-row"
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

    def __load_keybinds(self):
        # Will be as separate method, maybe in future will be used to retry
        try:
            self.settings_repository.load_keybinds()
        except FileNotFoundError as e:
            logger.warning("Could not load keybinds: %s", e)

    @work
    async def set_up_llm_stream_worker(self) -> None:
        """The only consumer of the LLM queue - status to input, entries to COMMS."""
        logger.debug("Starting to stream LLM items")
        async for item in self.dashboard_repository.stream_llm_responses():
            if isinstance(item, LLMStatus):
                self.query_one("#input-row", WidgetCommsInput).llm_state = item
            else:
                self.query_one("#comms-col", WidgetCommsCol).response_state = item

    def on_unmount(self) -> None:
        self.journal_watcher_service.stop_watcher_service()
