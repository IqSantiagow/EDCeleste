import contextvars
import logging
import threading

from textual.app import App, ComposeResult

from services.journal_watcher_service import JournalWatcherService
from ui.themes.themes import amber_theme
from ui.widgets.dashboard.ed_dashboard import EdDashboard
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
    ) -> None:
        super().__init__()
        self.journal_watcher_service = journal_watcher_service

    def on_mount(self) -> None:
        self.register_theme(amber_theme)
        self.theme = "amber"
        self.watcher_thread = threading.Thread(
            target=self.journal_watcher_service.start_watcher_service,
            daemon=True,
            context=contextvars.copy_context(),  # type: ignore
        )
        self.watcher_thread.start()
        logger.info(
            "UIApp mounted. JournalWatcherService started in a separate thread."
        )

    def on_unmount(self) -> None:
        logger.info("UIApp unmounted. Stopping JournalWatcherService.")
        self.journal_watcher_service.stop_watcher_service()

    def compose(self) -> ComposeResult:
        yield EdDashboard()
