from collections.abc import Callable
import logging
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container, HorizontalGroup
from textual.validation import Validator
from textual.widgets import Label
from textual.widgets import Input
from edceleste.ui.screens.settings.widgets.inputs.widget_base_input import (
    WidgetBaseInput,
)
from textual.reactive import reactive

from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)

logger = logging.getLogger(__name__)


class WidgetLabeledDynamicInputRow(WidgetBaseInput):
    DEFAULT_CLASSES = "entry-row-full"

    is_being_edited: reactive[bool] = reactive(False, recompose=True)

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
        """A row that shows the value as a Label and turns into an Input when
        clicked.

        on_submit is called with the new text every time the pilot finishes
        editing (Enter or leaving the field). type is the Textual Input type
        and must be "integer", "text" or "number". password=True hides the
        value behind dots, also when it is not being edited.
        """
        super().__init__(value=value, initial_value=value, **kwargs)
        self.label = label
        self.on_submit = on_submit
        self.type = type
        self.validators = validators if validators is not None else []
        self.password = password
        assert self.id is not None, "WidgetLabeledDynamicInputRow must have an id"
        assert self.type in ["integer", "text", "number"], (
            "Invalid input type. Must be 'integer', 'text', or 'number'."
        )

    def compose(self) -> ComposeResult:
        """Runs again every time is_being_edited flips.

        - editing -> an Input with the current value and the validators,
        - not editing -> a Label with the value (dots for a password). The
          label gets the yellow "warning-label" class when the value differs
          from the saved one.
        """
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
                    )
                if not self.is_being_edited:
                    displayed_value = (
                        "•" * len(self.value)
                        if self.password and self.value
                        else self.value
                    )
                    yield Label(
                        displayed_value,
                        classes="entry-value {}".format(
                            "warning-label" if self.value != self.initial_value else ""
                        ),
                    )

    def on_click(self, _: events.Click) -> None:
        """A click anywhere on the row switches it to edit mode. The Input only
        exists after the recompose, so focusing waits for the next refresh."""
        self.is_being_edited = True
        self.call_after_refresh(self.focus_input)

    def focus_input(self) -> None:
        """Puts the keyboard cursor into the Input, so the pilot can type
        right after the click."""
        self.query_one(Input).focus()

    def _submit_value(self, input_widget: Input) -> None:
        """Finishes editing with the text from the Input:
        1. posts ValueChanged, so the section container updates its settings,
        2. calls the on_submit callback,
        3. stores the text as the row value,
        4. leaves edit mode, which recomposes the row back to a Label.
        It always submits, also when the text did not change.
        """
        new_value = input_widget.value
        self._send_value_changed_event(new_value)
        self.on_submit(new_value)
        self.value = new_value
        self.is_being_edited = False

    @on(Input.Submitted)
    def handle_input_submitted(self, event: Input.Submitted) -> None:
        """Runs when the pilot presses Enter in the Input.

        When a validator fails, it shows a notification with the reasons and
        leaves edit mode without submitting, so the old value stays.
        """
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
        """Leaving the Input (click elsewhere, Tab) submits it like Enter, but
        without running the validators."""
        if self.is_being_edited:
            self._submit_value(self.query_one(Input))

    def _send_value_changed_event(self, new_value: str) -> None:
        """The message carries this row's id, so the container knows which
        settings field changed."""
        self.post_message(ValueChanged(self.id, new_value=new_value))  # type: ignore
