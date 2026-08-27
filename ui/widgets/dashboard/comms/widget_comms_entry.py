from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label

_TITLES = {
    "user-command": "YOU: ",
    "llm-response": "CELESTE: ",
    "system-message": "SYSTEM: ",
    "llm-action": "ACTION: ",
    "llm-error": "ERROR: ",
}


class WidgetCommsEntry(HorizontalGroup):
    def __init__(self, entry_type: str, content: str):
        super().__init__(classes=entry_type)
        self.entry_type = entry_type
        self.content = content

    def compose(self) -> ComposeResult:
        yield Label(_TITLES[self.entry_type], classes="comms-entry-title")
        yield Label(self.content, classes="comms-entry-content")
