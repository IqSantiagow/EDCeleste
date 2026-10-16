from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)

from textual.app import ComposeResult
from textual.widgets import Label, Select
from textual.containers import HorizontalGroup


from edceleste.ui.screens.settings.widgets.inputs.widget_base_input import (
    WidgetBaseInput,
)


class WidgetLabeledSelectRow(WidgetBaseInput):
    DEFAULT_CLASSES = "entry-row-full"

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
        super().__init__(*args, value=value, initial_value=value, **kwargs)
        self.label = label
        self.options = options
        self.values = values
        assert self.id is not None, "WidgetLabeledSelectRow must have an id"

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="settings-entry-row-container"):
            yield Label(self.label, classes="entry-label")
            # The persisted value may not be among the live-fetched options
            # (stale/renamed/removed voice, device removed, ...); Select raises
            # if its initial value isn't one of its options, so fall back to blank.
            effective_values = self.values if self.values is not None else self.options
            select_value = (
                self.initial_value
                if self.initial_value in effective_values
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

    def on_select_changed(self, event: Select.Changed) -> None:
        self.value = str(event.value)
        self.post_message(ValueChanged(self.id, self.value))  # type: ignore
