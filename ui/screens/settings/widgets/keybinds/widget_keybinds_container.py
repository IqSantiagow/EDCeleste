from textual.reactive import reactive
from textual.containers import HorizontalGroup, Vertical, VerticalScroll
from textual.widgets import Label

from services.models.keybinds_model import Keybind
from ui.screens.settings.settings_repository import SettingsRepository


class WidgetKeybindsContainer(Vertical):
    DEFAULT_CLASSES = "p-x-1"

    keybinds_state: reactive[list[Keybind]] = reactive([], recompose=True)

    def __init__(self, settings_repository: SettingsRepository) -> None:
        super().__init__()
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        self.keybinds_state = self.settings_repository.get_keybinds()

    def compose(self):
        yield Label("Loaded keybinds", id="keybinds-header-label", classes="text-bold")
        with VerticalScroll(id="keybinds-entry-container"):
            for keybind in self.keybinds_state:
                with HorizontalGroup(classes="keybinds-entry w-50"):
                    yield Label(
                        f"{keybind.action}",
                        classes="keybinds-action-label text-color-primary",
                    )
                    yield Label(
                        f"{keybind.key}",
                        classes=(
                            "keybinds-key-label text-color-primary "
                            "w-fill content-align-right"
                        ),
                    )
