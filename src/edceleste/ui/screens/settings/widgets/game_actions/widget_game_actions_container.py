import enum

from textual.app import ComposeResult
from textual.containers import Vertical

from edceleste.services.models.settings_model import GameActionsModel
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


class GameActionsInputWidgetIds(enum.StrEnum):
    GAME_ACTIONS_ENABLED_INPUT = "game-actions-enabled-input"


class WidgetGameActionsContainer(WidgetBaseSettingsContainer):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "GAME ACTIONS"

    def __init__(self, game_actions_model: GameActionsModel, *args, **kwargs) -> None:
        """game_actions_model is part of the screen's working copy of the
        settings and is changed in place."""
        super().__init__(*args, **kwargs)
        self.game_actions_model = game_actions_model

    def compose(self) -> ComposeResult:
        """Only one switch: whether Celeste may press game keys with the
        PerformGameAction tool."""
        yield from super().compose()
        with Vertical():
            yield WidgetSectionHeader("GAME ACTIONS")
            yield WidgetLabeledSwitchRow(
                "Enabled: ",
                value=self.game_actions_model.enabled,
                id=GameActionsInputWidgetIds.GAME_ACTIONS_ENABLED_INPUT,
            )

    def on_value_changed(self, message: ValueChanged) -> None:
        """Runs when the switch row posts ValueChanged. Writes the new on/off
        into the model and posts SectionSettingsChanged(GAME_ACTIONS) to the
        settings screen. Nothing is saved here."""
        if message.sender_id == GameActionsInputWidgetIds.GAME_ACTIONS_ENABLED_INPUT:
            self.game_actions_model.enabled = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.GAME_ACTIONS,
                new_value=self.game_actions_model,
            )
        )
