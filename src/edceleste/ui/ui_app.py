import logging
from textual.app import App
from edceleste.ui.screens.system_check.system_check_screen import (
    SystemCheckScreen,
)

from edceleste.services.game_watcher_service import GameWatcherService

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from edceleste.ui.themes.themes import amber_theme

from edceleste.ui.screens.dashboard.ed_dashboard_repository import EdDashboardRepository
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
        game_watcher_service: GameWatcherService = Provide[
            Container.game_watcher_service
        ],
        ed_dashboard_repository: EdDashboardRepository = Provide[
            Container.ed_dashboard_repository
        ],
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        system_check_repository=Provide[Container.system_check_repository],
    ) -> None:
        """Only keeps the injected services. The app itself owns no logic, it
        hands them to the screens it pushes."""
        super().__init__()
        self.game_watcher_service = game_watcher_service
        self.ed_dashboard_repository = ed_dashboard_repository
        self.settings_repository = settings_repository
        self.system_check_repository = system_check_repository

    def on_mount(self) -> None:
        """App start: switches to the amber theme and opens the system check
        screen first. The dashboard comes later, from
        open_dashboard_or_exit_after_system_check()."""
        self.register_theme(amber_theme)
        self.theme = "amber"
        self.push_screen(
            SystemCheckScreen(system_check_repository=self.system_check_repository),
            callback=self.open_dashboard_or_exit_after_system_check,
        )

    def open_dashboard_or_exit_after_system_check(self, result: bool | None) -> None:
        """Textual calls it when the system check screen is dismissed.
        True opens the dashboard. False or None (no result) logs an error and
        closes the whole app."""
        if result is None or not result:
            logger.error("System check failed. Exiting application.")
            self.exit()
            return
        self.push_screen(
            DashboardScreen(
                dashboard_repository=self.ed_dashboard_repository,
                settings_repository=self.settings_repository,
                game_watcher_service=self.game_watcher_service,
            )
        )

    def action_push_settings(self) -> None:
        """Bound to ctrl+r on the dashboard ("app.push_settings"). Opens the
        settings screen on top, so closing it brings the dashboard back."""
        self.push_screen(SettingsScreen(settings_repository=self.settings_repository))
