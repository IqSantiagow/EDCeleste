from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Static


class WidgetShipLogCol(Widget):
    DEFAULT_CLASSES = "col right-col"

    def compose(self) -> ComposeResult:
        yield Static(content="Ship log")
        with VerticalScroll():
            yield Label(content="test")
