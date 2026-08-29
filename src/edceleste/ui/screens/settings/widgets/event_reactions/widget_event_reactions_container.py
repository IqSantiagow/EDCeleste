import logging

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)

from edceleste.services.models.settings_model import SettingsModel
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

logger = logging.getLogger(__name__)

_CRITICAL_EVENTS = ["Died", "Resurrect"]
_NAVIGATION_EVENTS = [
    "StartJump",
    "FSDJump",
    "Location",
    "SupercruiseEntry",
    "SupercruiseExit",
    "SupercruiseDestinationDrop",
    "ApproachBody",
    "LeaveBody",
    "ApproachSettlement",
]
_DOCKING_EVENTS = ["Docked", "Undocked", "DockingGranted"]
_FUEL_EVENTS = ["FuelScoop", "ReservoirReplenished", "RefuelAll"]
_PROGRESSION_EVENTS = ["Rank", "Promotion", "Reputation"]
_SESSION_EVENTS = ["LoadGame", "Commander"]


class WidgetEventReactionsContainer(Vertical):
    def __init__(self, settings_model: SettingsModel, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.settings_model = settings_model

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield WidgetSectionHeader("CRITICAL")
            for event in _CRITICAL_EVENTS:
                yield WidgetLabeledSwitchRow(
                    event,
                    self.settings_model.event_reaction.reactions[event],
                    id=event,
                )
            yield WidgetSectionHeader("NAVIGATION")
            for event in _NAVIGATION_EVENTS:
                yield WidgetLabeledSwitchRow(
                    event,
                    self.settings_model.event_reaction.reactions[event],
                    id=event,
                )
            yield WidgetSectionHeader("DOCKING")
            for event in _DOCKING_EVENTS:
                yield WidgetLabeledSwitchRow(
                    event,
                    self.settings_model.event_reaction.reactions[event],
                    id=event,
                )
            yield WidgetSectionHeader("FUEL")
            for event in _FUEL_EVENTS:
                yield WidgetLabeledSwitchRow(
                    event,
                    self.settings_model.event_reaction.reactions[event],
                    id=event,
                )
            yield WidgetSectionHeader("PROGRESSION")
            for event in _PROGRESSION_EVENTS:
                yield WidgetLabeledSwitchRow(
                    event,
                    self.settings_model.event_reaction.reactions[event],
                    id=event,
                )
            yield WidgetSectionHeader("SESSION")
            for event in _SESSION_EVENTS:
                yield WidgetLabeledSwitchRow(
                    event,
                    self.settings_model.event_reaction.reactions[event],
                    id=event,
                )

    def on_value_changed(self, message: ValueChanged) -> None:
        if message.sender_id not in self.settings_model.event_reaction.reactions:
            logger.warning(
                f"Received ValueChanged for unknown event: {message.sender_id}"
            )
            return
        self.settings_model.event_reaction.reactions[message.sender_id] = (
            message.new_value
        )
        self.post_message(
            SectionSettingsChanged(
                SettingsSection.EVENT_REACTION,
                new_value=self.settings_model.event_reaction,
            )
        )
