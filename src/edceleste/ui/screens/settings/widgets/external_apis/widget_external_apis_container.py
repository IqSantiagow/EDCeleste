import enum

from textual.app import ComposeResult
from textual.containers import Vertical

from edceleste.services.models.settings_model import ExternalApisModel
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.widgets.const_ids import (
    SettingsSection,
)
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


class ExternalApisInputWidgetIds(enum.StrEnum):
    EXTERNAL_APIS_ENABLED_INPUT = "external-apis-enabled-input"


class WidgetExternalApisContainer(WidgetBaseSettingsContainer):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "EXTERNAL APIS"

    def __init__(self, external_apis_model: ExternalApisModel, *args, **kwargs) -> None:
        """external_apis_model is part of the screen's working copy of the
        settings and is changed in place."""
        super().__init__(*args, **kwargs)
        self.external_apis_model = external_apis_model

    def compose(self) -> ComposeResult:
        yield from super().compose()
        with Vertical():
            yield WidgetSectionHeader("EXTERNAL APIS")
            yield WidgetLabeledSwitchRow(
                "Enabled: ",
                value=self.external_apis_model.enabled,
                id=ExternalApisInputWidgetIds.EXTERNAL_APIS_ENABLED_INPUT,
            )

    def on_value_changed(self, message: ValueChanged) -> None:
        if message.sender_id == ExternalApisInputWidgetIds.EXTERNAL_APIS_ENABLED_INPUT:
            self.external_apis_model.enabled = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.EXTERNAL_APIS,
                new_value=self.external_apis_model,
            )
        )
