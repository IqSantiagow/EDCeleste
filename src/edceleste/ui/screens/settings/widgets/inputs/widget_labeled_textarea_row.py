from collections.abc import Callable
import logging
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, VerticalGroup
from textual.widgets import Label, TextArea
from edceleste.ui.screens.settings.widgets.inputs.widget_base_input import (
    WidgetBaseInput,
)
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)

logger = logging.getLogger(__name__)


class WidgetLabeledTextAreaRow(WidgetBaseInput):
    DEFAULT_CLASSES = "entry-row-full"

    def __init__(
        self,
        label: str,
        value: str,
        on_submit: Callable,
        **kwargs,
    ) -> None:
        super().__init__(value=value, initial_value=value, **kwargs)
        self.label = label
        self.on_submit = on_submit
        assert self.id is not None, "WidgetLabeledTextAreaRow must have an id"

    def compose(self) -> ComposeResult:
        with VerticalGroup():
            with HorizontalGroup(classes="textarea-row-label-line"):
                yield Label(self.label, classes="entry-label")
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
        self.post_message(ValueChanged(self.id, self.value))  # type: ignore
