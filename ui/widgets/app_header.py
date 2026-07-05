from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widget import Widget
from textual.widgets import Label


class AppHeader(HorizontalGroup):
    def __init__(self, content: Widget, **kwargs) -> None:
        super().__init__(id="app-header", **kwargs)
        self.content = content

    def compose(self) -> ComposeResult:
        yield Label(content="EDCELESTE", id="dashboard-title", classes="text-bold")
        yield self.content
