from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label


class WidgetCommsEntry(HorizontalGroup):
    def __init__(self, entry_type: str, content: str):
        super().__init__()
        self.entry_type = entry_type
        self.content = content

    def compose(self) -> ComposeResult:
        if self.entry_type == "user-command":
            yield Label(
                id="you-title", classes="human-command text-bold", content="YOU: "
            )
            yield Label(classes="human-command", content=self.content)
        elif self.entry_type == "llm-response":
            yield Label(
                id="celeste-title",
                classes="llm-response text-bold",
                content="CELESTE: ",
            )
            yield Label(classes="llm-response", content=self.content)
        elif self.entry_type == "system-message":
            yield Label(
                id="system-title",
                classes="system-message shady text-bold",
                content="SYSTEM: ",
            )
            yield Label(classes="system-message shady", content=self.content)
