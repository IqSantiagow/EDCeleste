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

    def __init__(
        self, label: str, value: bool, *args, hint: str = "", **kwargs
    ) -> None:
        """hint is an optional grey text shown right after the switch. An empty
        hint means no hint label at all."""
        super().__init__(*args, value=value, initial_value=value, **kwargs)
        self.value = value
        self.label = label
        self.hint = hint
        assert self.id is not None, "WidgetLabeledSwitchRow must have an id"

    def compose(self) -> ComposeResult:
        """Label on the left, then the switch, then the hint when there is
        one. The "with-hint" class changes the layout for that case."""
        with HorizontalGroup(id="settings-entry-row-container"):
            yield Label(self.label, classes="entry-label")
            # with a hint the switch sits next to the label and the hint follows it
            with Horizontal(
                id="settings-entry-value-container",
                classes="with-hint" if self.hint else "",
            ):
                yield Switch(value=self.value, classes="entry-switch")
                if self.hint:
                    yield Label(self.hint, classes="entry-hint")

    def on_switch_changed(self, event: Switch.Changed):
        """Stores the new on/off state and posts ValueChanged with it to the
        section container."""
        self.value = event.value
        self.post_message(ValueChanged(self.id, self.value))  # type: ignore
