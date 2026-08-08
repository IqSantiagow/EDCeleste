from textual.reactive import reactive
from ui.screens.settings.widgets.inputs.input_value_changed_event import ValueChanged
from ui.screens.settings.widgets.inputs.widget_settings_row import WidgetSettingsRow
from textual.app import ComposeResult
from textual.widgets import Label, Select
from textual.containers import HorizontalGroup


class WidgetLabeledSelectRow(WidgetSettingsRow):
    DEFAULT_CLASSES = "entry-row-full"
    _initial_value: str

    value: reactive[str] = reactive("")

    def __init__(
        self,
        label: str,
        options: list[str],
        value: str,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.label = label
        self.options = options
        self._initial_value = value
        self.value = value
        assert self.id is not None, "WidgetLabeledSelectRow must have an id"

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="settings-entry-row-container"):
            yield Label(self.label, classes="entry-label")
            yield Select.from_values(
                self.options,
                value=self._initial_value,
                classes="entry-select",
                compact=True,
            )
            yield Label(
                "◉ changed",
                classes="unsaved-changes-label warning-label {}".format(
                    "hidden" if self.value == self._initial_value else ""
                ),
                id="unsaved-changes-label",
            )

    def on_select_changed(self, event: Select.Changed) -> None:
        self.value = str(event.value)
        self.post_message(ValueChanged(self.id, self.value))  # type: ignore

    def watch_value(self, new_value: str) -> None:
        if self.is_mounted:
            if new_value != self._initial_value:
                self.query_one("#unsaved-changes-label", Label).remove_class("hidden")
            else:
                self.query_one("#unsaved-changes-label", Label).add_class("hidden")

    def notify_about_validation_failure(self, error_message: str) -> None:
        self.query_one(".unsaved-changes-label", Label).update("✘ invalid")
        self.query_one(".unsaved-changes-label", Label).add_class(
            "error"
        ).tooltip = error_message

    def reset_validation_state(self) -> None:
        # This method should be called when the settings are saved successfully
        self.query_one(".unsaved-changes-label", Label).update("◉ changed")
        self.query_one(".unsaved-changes-label", Label).remove_class("error")
        self.query_one(".unsaved-changes-label", Label).add_class(
            "hidden"
        ).with_tooltip(None)
        self._initial_value = self.value
