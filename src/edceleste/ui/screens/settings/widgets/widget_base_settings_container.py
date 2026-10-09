from textual.containers import Vertical
from textual.app import ComposeResult
from textual.widgets import Label

from edceleste.ui.screens.settings.widgets.inputs.widget_base_input import (
    WidgetBaseInput,
)


class ErrorContainer(Vertical):
    def compose(self) -> ComposeResult:
        """A "NOT SAVED" title and an empty message line. Starts hidden,
        show_validation_error() of the section container shows it."""
        yield Label("NOT SAVED", classes="error-label")
        yield Label("", classes="error-message-label")
        self.display = False


class WidgetBaseSettingsContainer(Vertical):
    def __init__(self, *args, **kwargs) -> None:
        """The id must be "settings-<section name>", e.g. "settings-tts". The
        settings screen finds the section for a save error by that id."""
        super().__init__(*args, **kwargs)
        assert self.id is not None, "WidgetBaseSettingsContainer must have an id"

    def compose(self) -> ComposeResult:
        """Only the hidden error box. Every section calls this first with
        `yield from super().compose()`, so the box sits on top."""
        yield ErrorContainer()

    def show_validation_error(self, error_message: str) -> None:
        """Called by the settings screen when saving failed because of this
        section. Shows the error box with "✗ <error_message>"."""
        self.query_one(ErrorContainer).display = True
        self.query_one(".error-message-label", Label).update(f"✗ {error_message}")

    def hide_error_and_mark_values_as_saved(self) -> None:
        """Called by the settings screen after a successful save:
        1. hides the error box and clears its message,
        2. marks the value of every input row in this section as saved, so
           is_modified() turns False.
        """
        self.query_one(ErrorContainer).display = False
        self.query_one(".error-message-label", Label).update("")
        for widget in self.query(WidgetBaseInput):
            widget.mark_current_value_as_saved()

    def is_modified(self) -> bool:
        """True when any input row in this section differs from its saved
        value. The settings screen uses it for the section and header
        markers."""
        return any(widget.is_modified() for widget in self.query(WidgetBaseInput))
