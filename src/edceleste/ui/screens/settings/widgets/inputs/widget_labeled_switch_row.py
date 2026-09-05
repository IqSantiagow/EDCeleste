import logging
from textual.app import ComposeResult
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from textual.containers import Horizontal, HorizontalGroup

from textual.widgets import Label, Switch
from edceleste.ui.screens.settings.widgets.inputs.widget_base_input import (
    WidgetBaseInput,
)


logger = logging.getLogger(__name__)


class WidgetLabeledSwitchRow(WidgetBaseInput):
    DEFAULT_CLASSES = "entry-row"

    def __init__(self, label: str, value: bool, *args, **kwargs) -> None:
        super().__init__(*args, value=value, initial_value=value, **kwargs)
        self.value = value
        self.label = label
        assert self.id is not None, "WidgetLabeledSwitchRow must have an id"

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="settings-entry-row-container"):
            yield Label(self.label, classes="entry-label")
            with Horizontal(id="settings-entry-value-container"):
                yield Switch(value=self.value, classes="entry-switch")

    def on_switch_changed(self, event: Switch.Changed):
        self.value = event.value
        self.post_message(ValueChanged(self.id, self.value))  # type: ignore
