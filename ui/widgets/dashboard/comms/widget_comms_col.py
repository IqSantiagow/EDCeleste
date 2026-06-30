from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Label

from ui.widgets.dashboard.comms.widget_comms_entry import WidgetCommsEntry
from ui.widgets.dashboard.comms.widget_comms_input import WidgetCommsInput


class WidgetCommsCol(Widget):
    DEFAULT_CLASSES = "col"

    def __init__(self) -> None:
        super().__init__()

    def on_mount(self) -> None:
        pass

    def compose(self) -> ComposeResult:
        yield Label(content="COMMS")
        with VerticalScroll():
            yield WidgetCommsEntry("user-command", "User called something")
            yield WidgetCommsEntry("user-command", "User called something")
        yield WidgetCommsInput()
