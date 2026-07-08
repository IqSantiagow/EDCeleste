from enum import Enum

from textual.reactive import reactive
from textual.app import ComposeResult
from textual.containers import Vertical

from ui.screens.settings.widgets.event_reactions import widget_event_reactions_container
from ui.screens.settings.widgets.keybinds import widget_keybinds_container
from ui.screens.settings.widgets.paths import widget_paths_container
from ui.screens.settings.widgets.system_prompts import widget_system_prompts_container


class SectionToShow(Enum):
    KEYBINDS = widget_keybinds_container.WidgetKeybindsContainer
    PATHS = widget_paths_container.WidgetPathsContainer
    EVENT_REACTIONS = widget_event_reactions_container.WidgetEventReactionsContainer
    SYSTEM_PROMPTS = widget_system_prompts_container.WidgetSystemPromptsContainer


class WidgetSettingsSectionContentColumn(Vertical):
    section_to_show_state: reactive[SectionToShow] = reactive(
        SectionToShow.KEYBINDS, recompose=True
    )

    def __init__(self, settings_repository, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings_repository = settings_repository

    def compose(self) -> ComposeResult:
        yield self.section_to_show_state.value(
            settings_repository=self.settings_repository
        )
