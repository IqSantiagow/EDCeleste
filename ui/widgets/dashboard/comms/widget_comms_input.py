from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Input


class WidgetCommsInput(Widget):
    def __init__(self) -> None:
        super().__init__()

    def on_mount(self) -> None:
        pass

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Input LLM command")
