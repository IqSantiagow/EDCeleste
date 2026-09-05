import enum
import logging

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from edceleste.services.models.journal_event import JournalEventType
from edceleste.services.models.settings_model import SettingsModel
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection
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

logger = logging.getLogger(__name__)


class EventReactionsInputWidgetIds(enum.Enum):
    DIED_INPUT = "died-input"
    RESURRECT_INPUT = "resurrect-input"
    START_JUMP_INPUT = "start-jump-input"
    FSD_JUMP_INPUT = "fsd-jump-input"
    LOCATION_INPUT = "location-input"
    SUPERCRUISE_ENTRY_INPUT = "supercruise-entry-input"
    SUPERCRUISE_EXIT_INPUT = "supercruise-exit-input"
    SUPERCRUISE_DESTINATION_DROP_INPUT = "supercruise-destination-drop-input"
    APPROACH_BODY_INPUT = "approach-body-input"
    LEAVE_BODY_INPUT = "leave-body-input"
    APPROACH_SETTLEMENT_INPUT = "approach-settlement-input"
    DOCKED_INPUT = "docked-input"
    UNDOCKED_INPUT = "undocked-input"
    DOCKING_GRANTED_INPUT = "docking-granted-input"
    FUEL_SCOOP_INPUT = "fuel-scoop-input"
    RESERVOIR_REPLENISHED_INPUT = "reservoir-replenished-input"
    REFUEL_ALL_INPUT = "refuel-all-input"
    RANK_INPUT = "rank-input"
    PROMOTION_INPUT = "promotion-input"
    REPUTATION_INPUT = "reputation-input"
    LOAD_GAME_INPUT = "load-game-input"
    COMMANDER_INPUT = "commander-input"


_EVENT_TYPES_BY_INPUT_WIDGET_ID = {
    EventReactionsInputWidgetIds.DIED_INPUT: JournalEventType.Died,
    EventReactionsInputWidgetIds.RESURRECT_INPUT: JournalEventType.Resurrect,
    EventReactionsInputWidgetIds.START_JUMP_INPUT: JournalEventType.StartJump,
    EventReactionsInputWidgetIds.FSD_JUMP_INPUT: JournalEventType.FSDJump,
    EventReactionsInputWidgetIds.LOCATION_INPUT: JournalEventType.Location,
    EventReactionsInputWidgetIds.SUPERCRUISE_ENTRY_INPUT: (
        JournalEventType.SupercruiseEntry
    ),
    EventReactionsInputWidgetIds.SUPERCRUISE_EXIT_INPUT: (
        JournalEventType.SupercruiseExit
    ),
    EventReactionsInputWidgetIds.SUPERCRUISE_DESTINATION_DROP_INPUT: (
        JournalEventType.SupercruiseDestinationDrop
    ),
    EventReactionsInputWidgetIds.APPROACH_BODY_INPUT: JournalEventType.ApproachBody,
    EventReactionsInputWidgetIds.LEAVE_BODY_INPUT: JournalEventType.LeaveBody,
    EventReactionsInputWidgetIds.APPROACH_SETTLEMENT_INPUT: (
        JournalEventType.ApproachSettlement
    ),
    EventReactionsInputWidgetIds.DOCKED_INPUT: JournalEventType.Docked,
    EventReactionsInputWidgetIds.UNDOCKED_INPUT: JournalEventType.Undocked,
    EventReactionsInputWidgetIds.DOCKING_GRANTED_INPUT: JournalEventType.DockingGranted,
    EventReactionsInputWidgetIds.FUEL_SCOOP_INPUT: JournalEventType.FuelScoop,
    EventReactionsInputWidgetIds.RESERVOIR_REPLENISHED_INPUT: (
        JournalEventType.ReservoirReplenished
    ),
    EventReactionsInputWidgetIds.REFUEL_ALL_INPUT: JournalEventType.RefuelAll,
    EventReactionsInputWidgetIds.RANK_INPUT: JournalEventType.Rank,
    EventReactionsInputWidgetIds.PROMOTION_INPUT: JournalEventType.Promotion,
    EventReactionsInputWidgetIds.REPUTATION_INPUT: JournalEventType.Reputation,
    EventReactionsInputWidgetIds.LOAD_GAME_INPUT: JournalEventType.LoadGame,
    EventReactionsInputWidgetIds.COMMANDER_INPUT: JournalEventType.Commander,
}


_CRITICAL_EVENTS = [
    EventReactionsInputWidgetIds.DIED_INPUT,
    EventReactionsInputWidgetIds.RESURRECT_INPUT,
]
_NAVIGATION_EVENTS = [
    EventReactionsInputWidgetIds.START_JUMP_INPUT,
    EventReactionsInputWidgetIds.FSD_JUMP_INPUT,
    EventReactionsInputWidgetIds.LOCATION_INPUT,
    EventReactionsInputWidgetIds.SUPERCRUISE_ENTRY_INPUT,
    EventReactionsInputWidgetIds.SUPERCRUISE_EXIT_INPUT,
    EventReactionsInputWidgetIds.SUPERCRUISE_DESTINATION_DROP_INPUT,
    EventReactionsInputWidgetIds.APPROACH_BODY_INPUT,
    EventReactionsInputWidgetIds.LEAVE_BODY_INPUT,
    EventReactionsInputWidgetIds.APPROACH_SETTLEMENT_INPUT,
]
_DOCKING_EVENTS = [
    EventReactionsInputWidgetIds.DOCKED_INPUT,
    EventReactionsInputWidgetIds.UNDOCKED_INPUT,
    EventReactionsInputWidgetIds.DOCKING_GRANTED_INPUT,
]
_FUEL_EVENTS = [
    EventReactionsInputWidgetIds.FUEL_SCOOP_INPUT,
    EventReactionsInputWidgetIds.RESERVOIR_REPLENISHED_INPUT,
    EventReactionsInputWidgetIds.REFUEL_ALL_INPUT,
]
_PROGRESSION_EVENTS = [
    EventReactionsInputWidgetIds.RANK_INPUT,
    EventReactionsInputWidgetIds.PROMOTION_INPUT,
    EventReactionsInputWidgetIds.REPUTATION_INPUT,
]
_SESSION_EVENTS = [
    EventReactionsInputWidgetIds.LOAD_GAME_INPUT,
    EventReactionsInputWidgetIds.COMMANDER_INPUT,
]


class WidgetEventReactionsContainer(WidgetBaseSettingsContainer):
    def __init__(self, settings_model: SettingsModel, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.settings_model = settings_model

    def compose(self) -> ComposeResult:
        yield from super().compose()
        with VerticalScroll():
            yield WidgetSectionHeader("CRITICAL")
            for event_input_widget_id in _CRITICAL_EVENTS:
                event_type = _EVENT_TYPES_BY_INPUT_WIDGET_ID[event_input_widget_id]
                yield WidgetLabeledSwitchRow(
                    event_type.value,
                    self.settings_model.event_reactions.reactions[event_type.value],
                    id=event_input_widget_id.value,
                )
            yield WidgetSectionHeader("NAVIGATION")
            for event_input_widget_id in _NAVIGATION_EVENTS:
                event_type = _EVENT_TYPES_BY_INPUT_WIDGET_ID[event_input_widget_id]
                yield WidgetLabeledSwitchRow(
                    event_type.value,
                    self.settings_model.event_reactions.reactions[event_type.value],
                    id=event_input_widget_id.value,
                )
            yield WidgetSectionHeader("DOCKING")
            for event_input_widget_id in _DOCKING_EVENTS:
                event_type = _EVENT_TYPES_BY_INPUT_WIDGET_ID[event_input_widget_id]
                yield WidgetLabeledSwitchRow(
                    event_type.value,
                    self.settings_model.event_reactions.reactions[event_type.value],
                    id=event_input_widget_id.value,
                )
            yield WidgetSectionHeader("FUEL")
            for event_input_widget_id in _FUEL_EVENTS:
                event_type = _EVENT_TYPES_BY_INPUT_WIDGET_ID[event_input_widget_id]
                yield WidgetLabeledSwitchRow(
                    event_type.value,
                    self.settings_model.event_reactions.reactions[event_type.value],
                    id=event_input_widget_id.value,
                )
            yield WidgetSectionHeader("PROGRESSION")
            for event_input_widget_id in _PROGRESSION_EVENTS:
                event_type = _EVENT_TYPES_BY_INPUT_WIDGET_ID[event_input_widget_id]
                yield WidgetLabeledSwitchRow(
                    event_type.value,
                    self.settings_model.event_reactions.reactions[event_type.value],
                    id=event_input_widget_id.value,
                )
            yield WidgetSectionHeader("SESSION")
            for event_input_widget_id in _SESSION_EVENTS:
                event_type = _EVENT_TYPES_BY_INPUT_WIDGET_ID[event_input_widget_id]
                yield WidgetLabeledSwitchRow(
                    event_type.value,
                    self.settings_model.event_reactions.reactions[event_type.value],
                    id=event_input_widget_id.value,
                )

    def on_value_changed(self, message: ValueChanged) -> None:
        try:
            event_input_widget_id = EventReactionsInputWidgetIds(message.sender_id)
        except ValueError:
            logger.warning(
                f"Received ValueChanged for unknown input: {message.sender_id}"
            )
            return
        event_type = _EVENT_TYPES_BY_INPUT_WIDGET_ID[event_input_widget_id]
        self.settings_model.event_reactions.reactions[event_type.value] = (
            message.new_value
        )
        self.post_message(
            SectionSettingsChanged(
                SettingsSection.EVENT_REACTIONS,
                new_value=self.settings_model.event_reactions,
            )
        )
