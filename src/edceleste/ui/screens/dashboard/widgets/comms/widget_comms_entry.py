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
        """entry_type must be one of the _TITLES keys. It is also set as the CSS
        class, so css.tcss colours the line by who said it."""
        super().__init__(classes=entry_type)
        self.entry_type = entry_type
        self.content = content

    def compose(self) -> ComposeResult:
        """Two labels on one line: the speaker title ("YOU: ", "CELESTE: ",
        ...) and the text. An entry_type not in _TITLES raises KeyError
        here."""
        yield Label(_TITLES[self.entry_type], classes="comms-entry-title")
        yield Label(self.content, classes="comms-entry-content")
