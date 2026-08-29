from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label


class WidgetLabeledValueRow(HorizontalGroup):
    DEFAULT_CLASSES = "entry-row"

    def __init__(self, label: str, value: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.value = value

    def compose(self) -> ComposeResult:
        yield Label(self.label, classes="entry-label")
        yield Label(self.value, classes="entry-value")
