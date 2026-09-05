from collections.abc import Callable
import logging
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, VerticalGroup
from textual.widgets import Label, TextArea

from edceleste.ui.screens.settings.widgets.inputs.widget_settings_row import (
    WidgetSettingsRow,
)
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)

logger = logging.getLogger(__name__)


class WidgetLabeledTextAreaRow(WidgetSettingsRow):
    DEFAULT_CLASSES = "entry-row-full"

    _initial_value: str

    def __init__(
        self,
        label: str,
        value: str,
        on_submit: Callable,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.value = value
        self._initial_value = value
        self.on_submit = on_submit
        assert self.id is not None, "WidgetLabeledTextAreaRow must have an id"

    def compose(self) -> ComposeResult:
        with VerticalGroup():
            with HorizontalGroup(classes="textarea-row-label-line"):
                yield Label(self.label, classes="entry-label")
                yield Label(
                    "◉ changed",
                    classes="unsaved-changes-label warning-label hidden",
                    id="unsaved-changes-label",
                )
            yield TextArea(
                self.value,
                classes="entry-textarea",
                compact=True,
                highlight_cursor_line=False,
            )

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        new_value = event.text_area.text
        self.value = new_value
        self.on_submit(new_value)
        self.post_message(ValueChanged(self.id, new_value=new_value))  # type: ignore

        changed_label = self.query_one("#unsaved-changes-label", Label)
        if new_value != self._initial_value:
            changed_label.remove_class("hidden")
        else:
            changed_label.add_class("hidden")

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
