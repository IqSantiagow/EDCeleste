import asyncio
import logging
import threading

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.widgets import Footer, Label

from services.journal_watcher_service import JournalWatcherService
from services.tts_service import TTSService
from ui.screens.settings.settings_repository import SettingsRepository
from ui.screens.settings.settings_screen import SettingsScreen
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
        ("ctrl+s", "push_settings", "Settings"),
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
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        tts_service: TTSService = Provide[Container.tts_service],
    ) -> None:
        super().__init__()
        self.journal_watcher_service = journal_watcher_service
        self.ed_dashboard_presenter = ed_dashboard_presenter
        self.settings_repository = settings_repository
        self.tts_service = tts_service

    def on_mount(self) -> None:
        self.register_theme(amber_theme)
        self.theme = "amber"
        self.watcher_thread = threading.Thread(
            target=lambda: asyncio.run(
                self.journal_watcher_service.start_watcher_service()
            ),
            daemon=True,
        )
        self.watcher_thread.start()
        asyncio.create_task(self.__load_keybinds())

    def on_unmount(self) -> None:
        logger.info("UIApp unmounted. Stopping JournalWatcherService.")
        self.journal_watcher_service.stop_watcher_service()

    def compose(self) -> ComposeResult:
        with Grid(id="app-container", classes="screen-grid"):
            yield AppHeader(content=DashboardStatsContent())
            yield Label(id="comms-title", classes="shady header-title", content="COMMS")
            yield Label(
                id="ship-log-title", classes="shady header-title", content="SHIP LOG"
            )
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

    def action_push_settings(self) -> None:
        self.push_screen(SettingsScreen(settings_repository=self.settings_repository))

    async def __load_keybinds(self):
        # Will be as separate method, maybe in future will be used to retry
        try:
            await self.settings_repository.load_keybinds()
        except FileNotFoundError as e:
            logger.warning("Could not load keybinds: %s", e)
