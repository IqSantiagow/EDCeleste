from collections.abc import Callable
import logging
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container, HorizontalGroup
from textual.validation import Validator
from textual.widgets import Label
from textual.widgets import Input
from textual.reactive import reactive

from edceleste.ui.screens.settings.widgets.inputs.widget_settings_row import (
    WidgetSettingsRow,
)
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)

logger = logging.getLogger(__name__)


class WidgetLabeledDynamicInputRow(WidgetSettingsRow):
    DEFAULT_CLASSES = "entry-row-full"

    is_being_edited: reactive[bool] = reactive(False, recompose=True)

    _initial_value: str

    def __init__(
        self,
        label: str,
        value: str,
        on_submit: Callable,
        type: str,
        validators: list[Validator] | None = None,
        password: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.value = value
        self._initial_value = value
        self.on_submit = on_submit
        self.type = type
        self.validators = validators if validators is not None else []
        self.password = password
        assert self.id is not None, "WidgetLabeledDynamicInputRow must have an id"
        assert self.type in ["integer", "text", "number"], (
            "Invalid input type. Must be 'integer', 'text', or 'number'."
        )

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="settings-entry-row-container"):
            yield Label(self.label, classes="entry-label")
            with Container(id="settings-entry-value-container"):
                if self.is_being_edited:
                    yield Input(
                        self.value,
                        classes="entry-input",
                        type=self.type,  # type: ignore
                        validators=self.validators,
                        password=self.password,
                        compact=True,
                    ).focus()
                if not self.is_being_edited:
                    displayed_value = (
                        "•" * len(self.value)
                        if self.password and self.value
                        else self.value
                    )
                    yield Label(
                        displayed_value,
                        classes="entry-value {}".format(
                            "warning-label" if self.value != self._initial_value else ""
                        ),
                    )
            yield Label(
                "◉ changed",
                classes="unsaved-changes-label warning-label {}".format(
                    "hidden" if self.value == self._initial_value else ""
                ),
                id="unsaved-changes-label",
            )

    def on_click(self, _: events.Click) -> None:
        self.is_being_edited = True

    def _submit_value(self, input_widget: Input) -> None:
        new_value = input_widget.value
        self._send_value_changed_event(new_value)
        self.on_submit(new_value)
        self.value = new_value
        self.is_being_edited = False

    @on(Input.Submitted)
    def handle_input_submitted(self, event: Input.Submitted) -> None:
        if event.validation_result is not None and not event.validation_result.is_valid:
            failure_descriptions = " ".join(
                event.validation_result.failure_descriptions
            )
            self.notify(f"Invalid input: {failure_descriptions}")
            self.is_being_edited = False
            return
        if self.is_being_edited:
            self._submit_value(event.input)

    def on_descendant_blur(self, _: events.DescendantBlur) -> None:
        if self.is_being_edited:
            self._submit_value(self.query_one(Input))

    def _send_value_changed_event(self, new_value: str) -> None:
        self.post_message(ValueChanged(self.id, new_value=new_value))  # type: ignore

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
        self.query_one(".entry-value", Label).remove_class("warning-label")
        self._initial_value = self.value
