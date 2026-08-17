import logging

from textual.app import ComposeResult
from textual.containers import Horizontal, HorizontalGroup
from textual.widgets import Label, Switch

from ui.screens.settings.widgets.inputs.widget_settings_row import WidgetSettingsRow

logger = logging.getLogger(__name__)


class WidgetLabeledSwitchRow(WidgetSettingsRow):
    DEFAULT_CLASSES = "entry-row"
    _initial_value: bool

    def __init__(self, label: str, value: bool, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._initial_value = value
        self.value = value
        self.label = label
        assert self.id is not None, "WidgetLabeledSwitchRow must have an id"

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="settings-entry-row-container"):
            yield Label(self.label, classes="entry-label")
            with Horizontal(id="settings-entry-value-container"):
                yield Switch(value=self.value, classes="entry-switch")
                yield Label(
                    "◉ changed",
                    classes="unsaved-changes-label warning-label {}".format(
                        "hidden" if self.value == self._initial_value else ""
                    ),
                    id="unsaved-changes-label",
                )

    def on_switch_changed(self, event: Switch.Changed):
        self.value = event.value
        if self.value != self._initial_value:
            self.query_one("#unsaved-changes-label", Label).remove_class("hidden")
        else:
            self.query_one("#unsaved-changes-label", Label).add_class("hidden")

    def notify_about_validation_failure(self, error_message: str) -> None:
        # Validation will be handled by the parent container
        ...

    def reset_validation_state(self) -> None:
        # This method should be called when the settings are saved successfully
        self.query_one(".unsaved-changes-label", Label).update("◉ changed")
        self.query_one(".unsaved-changes-label", Label).remove_class("error")
        self.query_one(".unsaved-changes-label", Label).add_class(
            "hidden"
        ).with_tooltip(None)
        self._initial_value = self.value
