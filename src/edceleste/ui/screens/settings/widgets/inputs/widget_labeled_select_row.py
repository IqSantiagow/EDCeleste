from textual.reactive import reactive
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_settings_row import (
    WidgetSettingsRow,
)
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
        values: list[str] | None = None,
        *args,
        **kwargs,
    ):
        """
        Parameters
        ----------
        label:
            Row label shown on the left.
        options:
            Human-readable display strings shown in the dropdown.
        value:
            The currently selected *stored* value (matched against `values` when
            provided, or against `options` when `values` is None).
        values:
            Optional list of stored values that correspond 1-to-1 with
            `options`.  When given, the dropdown shows `options` labels but
            emits and receives items from `values`.  Useful when you want to
            display a friendly name but store a compact key (e.g. a device
            index as a string).
        """
        super().__init__(*args, **kwargs)
        self.label = label
        self.options = options
        self.values = values
        self._initial_value = value
        self.value = value
        assert self.id is not None, "WidgetLabeledSelectRow must have an id"

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="settings-entry-row-container"):
            yield Label(self.label, classes="entry-label")
            # The persisted value may not be among the live-fetched options
            # (stale/renamed/removed voice, device removed, ...); Select raises
            # if its initial value isn't one of its options, so fall back to blank.
            effective_values = self.values if self.values is not None else self.options
            select_value = (
                self._initial_value
                if self._initial_value in effective_values
                else Select.NULL
            )
            if self.values is not None:
                yield Select(
                    list(zip(self.options, self.values)),
                    value=select_value,
                    classes="entry-select",
                    compact=True,
                )
            else:
                yield Select.from_values(
                    self.options,
                    value=select_value,
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
