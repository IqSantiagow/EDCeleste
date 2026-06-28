from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label


class WidgetCommsEntry(Widget):
    def __init__(self, entry_type: str, content: str):
        super().__init__()
        self.entry_type = entry_type
        self.content = content

    def compose(self) -> ComposeResult:
        if self.entry_type == "user-command":
            with Horizontal():
                yield Label(id="you-title", classes="human-command", content="YOU: ")
                yield Label(classes="human-command", content=self.content)
