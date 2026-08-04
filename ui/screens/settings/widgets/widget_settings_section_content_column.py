from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import ContentSwitcher
from services.models.keybinds_model import Keybind
from services.models.settings_model import SettingsModel
from ui.screens.settings.widgets.event_reactions import widget_event_reactions_container
from ui.screens.settings.widgets.keybinds import widget_keybinds_container
from ui.screens.settings.widgets.paths import widget_paths_container
from ui.screens.settings.widgets.system_prompts import widget_system_prompts_container


class WidgetSettingsSectionContentColumn(Vertical):
    def __init__(
        self, settings: SettingsModel, keybinds: list[Keybind], *args, **kwargs
    ):
        # TODO: Think about how to handle keybinds better
        super().__init__(*args, **kwargs)
        self.settings = settings
        self.keybinds = keybinds

    def compose(self) -> ComposeResult:
        with ContentSwitcher(
            initial="settings-keybinds",
            id="settings-content-switcher",
        ):
            yield widget_keybinds_container.WidgetKeybindsContainer(
                keybinds=self.keybinds,
                id="settings-keybinds",
            )
            yield widget_paths_container.WidgetPathsContainer(
                path_model=self.settings.paths,
                id="settings-paths",
            )
            yield widget_event_reactions_container.WidgetEventReactionsContainer(
                settings_model=self.settings,
                id="settings-event-reactions",
            )
            yield widget_system_prompts_container.WidgetSystemPromptsContainer(
                llm_model=self.settings.llm,
                id="settings-llm",
            )
