from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label


class WidgetShipLogEntry(HorizontalGroup):
    def __init__(self, timestamp: str, event: str, details: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.timestamp = timestamp
        self.event = event
        self.details = details

    def compose(self) -> ComposeResult:
        yield Label(content=self.timestamp, classes="shady")
        yield Label(content=self.event, classes="text-bold")
        yield Label(content=self.details)
