import enum

from textual.app import ComposeResult
from textual.containers import Vertical
from edceleste.ui.screens.settings.events.settings_events import (
    SectionSettingsChanged,
)
from edceleste.ui.screens.settings.widgets.const_ids import (
    SettingsSection,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_dynamic_input_row import (  # noqa: E501
    ValueChanged,
    WidgetLabeledDynamicInputRow,
)

from edceleste.services.models.settings_model import PathModel

from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)


class PathsInputWidgetIds(enum.Enum):
    JOURNAL_PATH_INPUT = "journal-path-input"
    KEYBINDS_PATH_INPUT = "keybinds-path-input"


class WidgetPathsContainer(WidgetBaseSettingsContainer):
    def __init__(self, path_model: PathModel, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.path_model = path_model

    def compose(self) -> ComposeResult:
        yield from super().compose()
        with Vertical():
            yield WidgetSectionHeader("GAME DATA")
            yield WidgetLabeledDynamicInputRow(
                "Journal Path:",
                f"{self.path_model.journal_path}",
                # TODO: Implement validation logic
                lambda value: self.log(f"Journal Path submitted: {value}"),
                type="text",
                id=PathsInputWidgetIds.JOURNAL_PATH_INPUT.value,
            )
            yield WidgetLabeledDynamicInputRow(
                "Keybinds Path:",
                f"{self.path_model.keybindings_path}",
                # TODO: Implement validation logic
                lambda value: self.log(f"Keybinds Path submitted: {value}"),
                type="text",
                id=PathsInputWidgetIds.KEYBINDS_PATH_INPUT.value,
            )
            yield WidgetSectionHeader("APP SETTINGS")

    def on_value_changed(self, message: ValueChanged) -> None:
        if message.sender_id == PathsInputWidgetIds.JOURNAL_PATH_INPUT.value:
            self.path_model.journal_path = message.new_value
        elif message.sender_id == PathsInputWidgetIds.KEYBINDS_PATH_INPUT.value:
            self.path_model.keybindings_path = message.new_value

        self.post_message(
            SectionSettingsChanged(SettingsSection.PATHS, new_value=self.path_model)
        )
