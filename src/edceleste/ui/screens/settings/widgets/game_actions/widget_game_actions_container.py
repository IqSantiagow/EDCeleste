from textual.app import ComposeResult
from textual.containers import Vertical

from edceleste.services.models.settings_model import GameActionsModel
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.widgets.const_ids import (
    SettingsInputWidgetIds,
    SettingsSection,
)
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


class WidgetGameActionsContainer(Vertical):
    def __init__(self, game_actions_model: GameActionsModel, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.game_actions_model = game_actions_model

    def compose(self) -> ComposeResult:
        with Vertical():
            yield WidgetSectionHeader("GAME ACTIONS")
            yield WidgetLabeledSwitchRow(
                "Enabled: ",
                value=self.game_actions_model.enabled,
                id=SettingsInputWidgetIds.GAME_ACTIONS_ENABLED_INPUT.value,
            )

    def on_value_changed(self, message: ValueChanged) -> None:
        if (
            message.sender_id
            == SettingsInputWidgetIds.GAME_ACTIONS_ENABLED_INPUT.value
        ):
            self.game_actions_model.enabled = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.GAME_ACTIONS,
                new_value=self.game_actions_model,
            )
        )
