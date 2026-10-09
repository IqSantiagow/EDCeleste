from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label


class WidgetLabeledValueRow(HorizontalGroup):
    DEFAULT_CLASSES = "entry-row"

    def __init__(self, label: str, value: str, **kwargs) -> None:
        """Only keeps both texts, the Labels are built in compose()."""
        super().__init__(**kwargs)
        self.label = label
        self.value = value

    def compose(self) -> ComposeResult:
        """Label on the left, value on the right, styled by the entry-label and
        entry-value classes in ui/css.tcss. The texts are drawn once: changing
        self.label or self.value later does not redraw the row."""
        yield Label(self.label, classes="entry-label")
        yield Label(self.value, classes="entry-value")
