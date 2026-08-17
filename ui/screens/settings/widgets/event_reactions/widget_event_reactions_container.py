from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll

from services.models.settings_model import SettingsModel
from ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from ui.widgets.common.widget_section_header import WidgetSectionHeader

_NAVIGATION_EVENTS = []


class WidgetEventReactionsContainer(Vertical):
    def __init__(self, settings_model: SettingsModel, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.settings_model = settings_model

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield WidgetSectionHeader("CRITICAL")
            for event, value in self.settings_model.event_reaction.items():
                yield WidgetLabeledSwitchRow(event, value, id=event)
            # yield WidgetSectionHeader("NAVIGATION")
            # yield WidgetSectionHeader("DOCKING")
            # yield WidgetSectionHeader("FUEL")
            # yield WidgetSectionHeader("PROGRESSION")
            # yield WidgetSectionHeader("SESSION")
