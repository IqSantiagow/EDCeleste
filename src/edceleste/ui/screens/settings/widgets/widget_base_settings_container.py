from textual.containers import Vertical
from textual.app import ComposeResult
from textual.widgets import Label

from edceleste.ui.screens.settings.widgets.inputs.widget_base_input import (
    WidgetBaseInput,
)


class ErrorContainer(Vertical):
    def compose(self) -> ComposeResult:
        yield Label("NOT SAVED", classes="error-label")
        yield Label("", classes="error-message-label")
        self.display = False


class WidgetBaseSettingsContainer(Vertical):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        assert self.id is not None, "WidgetBaseSettingsContainer must have an id"

    def compose(self) -> ComposeResult:
        yield ErrorContainer()

    def show_validation_error(self, error_message: str) -> None:
        self.query_one(ErrorContainer).display = True
        self.query_one(".error-message-label", Label).update(f"✗ {error_message}")

    def reset_validation_state(self) -> None:
        self.query_one(ErrorContainer).display = False
        self.query_one(".error-message-label", Label).update("")
        for widget in self.query(WidgetBaseInput):
            widget.reset_current_value()

    def is_modified(self) -> bool:
        for widget in self.query(WidgetBaseInput):
            if widget.is_modified():
                return True
        return False
