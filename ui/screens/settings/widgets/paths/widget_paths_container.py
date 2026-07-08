from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label

from ui.screens.settings.settings_repository import SettingsRepository


class WidgetPathsContainer(Vertical):
    DEFAULT_CLASSES = "p-x-1"

    def __init__(self, settings_repository: SettingsRepository) -> None:
        super().__init__()
        self.settings_repository = settings_repository

    def compose(self) -> ComposeResult:
        yield Label("PATHS", id="settings-paths-label")
