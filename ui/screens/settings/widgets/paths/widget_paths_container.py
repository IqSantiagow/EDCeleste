from textual.app import ComposeResult
from textual.containers import Vertical
from ui.screens.settings.events.settings_events import (
    SectionSettingsChanged,
)
from ui.screens.settings.widgets.const_ids import (
    SettingsInputWidgetIds,
    SettingsSection,
)
from ui.screens.settings.widgets.widget_labeled_dynamic_input_row import (
    ValueChanged,
    WidgetLabeledDynamicInputRow,
)

from services.models.settings_model import PathModel

from ui.widgets.common.widget_section_header import WidgetSectionHeader


class WidgetPathsContainer(Vertical):
    def __init__(self, path_model: PathModel, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.path_model = path_model

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-paths-entry-container"):
            yield WidgetSectionHeader("GAME DATA")
            yield WidgetLabeledDynamicInputRow(
                "Journal Path:",
                f"{self.path_model.journal_path}",
                # TODO: Implement validation logic
                lambda value: self.log(f"Journal Path submitted: {value}"),
                id=SettingsInputWidgetIds.JOURNAL_PATH_INPUT.value,
            )
            yield WidgetLabeledDynamicInputRow(
                "Keybinds Path:",
                f"{self.path_model.keybindings_path}",
                # TODO: Implement validation logic
                lambda value: self.log(f"Keybinds Path submitted: {value}"),
                id=SettingsInputWidgetIds.KEYBINDS_PATH_INPUT.value,
            )
            yield WidgetSectionHeader("APP SETTINGS")

    def on_value_changed(self, message: ValueChanged) -> None:
        if message.sender_id == SettingsInputWidgetIds.JOURNAL_PATH_INPUT.value:
            self.path_model.journal_path = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.KEYBINDS_PATH_INPUT.value:
            self.path_model.keybindings_path = message.new_value

        self.post_message(
            SectionSettingsChanged(SettingsSection.PATHS, new_value=self.path_model)
        )
