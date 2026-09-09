import logging
from textual.app import App
from edceleste.ui.screens.system_check.system_check_screen import (
    SystemCheckScreen,
)

from edceleste.services.journal_watcher_service import JournalWatcherService

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from edceleste.ui.themes.themes import amber_theme

from edceleste.ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository
from edceleste.containers.main_container import Container
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
        ed_dashboard_repository: EdDashboardRepository = Provide[
            Container.ed_dashboard_repository
        ],
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        system_check_repository=Provide[Container.system_check_repository],
    ) -> None:
        super().__init__()
        self.journal_watcher_service = journal_watcher_service
        self.ed_dashboard_repository = ed_dashboard_repository
        self.settings_repository = settings_repository
        self.system_check_repository = system_check_repository

    def on_mount(self) -> None:
        self.register_theme(amber_theme)
        self.theme = "amber"
        self.push_screen(
            SystemCheckScreen(system_check_repository=self.system_check_repository),
            callback=self.handle_system_check_result,
        )

    def handle_system_check_result(self, result: bool | None) -> None:
        if result is None or not result:
            logger.error("System check failed. Exiting application.")
            self.exit()
            return
        self.push_screen(
            DashboardScreen(
                ed_dashboard_repository=self.ed_dashboard_repository,
                settings_repository=self.settings_repository,
                journal_watcher_service=self.journal_watcher_service,
            )
        )

    def action_push_settings(self) -> None:
        self.push_screen(SettingsScreen(settings_repository=self.settings_repository))
