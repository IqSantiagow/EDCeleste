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


class PathsInputWidgetIds(enum.StrEnum):
    JOURNAL_PATH_INPUT = "journal-path-input"
    KEYBINDS_PATH_INPUT = "keybinds-path-input"


class WidgetPathsContainer(WidgetBaseSettingsContainer):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "PATHS"

    def __init__(self, path_model: PathModel, *args, **kwargs) -> None:
        """path_model is part of the screen's working copy of the settings and
        is changed in place."""
        super().__init__(*args, **kwargs)
        self.path_model = path_model

    def compose(self) -> ComposeResult:
        """Two click to edit text rows, the journal folder and the keybinds
        file. Their on_submit callbacks only log, the paths are not checked.
        The "APP SETTINGS" header has no rows under it yet."""
        yield from super().compose()
        with Vertical():
            yield WidgetSectionHeader("GAME DATA")
            yield WidgetLabeledDynamicInputRow(
                "Journal Path:",
                f"{self.path_model.journal_path}",
                # TODO: Implement validation logic
                lambda value: self.log(f"Journal Path submitted: {value}"),
                type="text",
                id=PathsInputWidgetIds.JOURNAL_PATH_INPUT,
            )
            yield WidgetLabeledDynamicInputRow(
                "Keybinds Path:",
                f"{self.path_model.keybindings_path}",
                # TODO: Implement validation logic
                lambda value: self.log(f"Keybinds Path submitted: {value}"),
                type="text",
                id=PathsInputWidgetIds.KEYBINDS_PATH_INPUT,
            )
            yield WidgetSectionHeader("APP SETTINGS")

    def on_value_changed(self, message: ValueChanged) -> None:
        """Runs when a path row posts ValueChanged. Writes the new text into
        journal_path or keybindings_path and posts SectionSettingsChanged(PATHS)
        to the settings screen. Nothing is saved here."""
        if message.sender_id == PathsInputWidgetIds.JOURNAL_PATH_INPUT:
            self.path_model.journal_path = message.new_value
        elif message.sender_id == PathsInputWidgetIds.KEYBINDS_PATH_INPUT:
            self.path_model.keybindings_path = message.new_value

        self.post_message(
            SectionSettingsChanged(SettingsSection.PATHS, new_value=self.path_model)
        )
