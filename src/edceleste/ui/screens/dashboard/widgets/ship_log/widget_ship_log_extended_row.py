from datetime import datetime

from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label

from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    JournalLogViewModel,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_row import (
    CATEGORY_MARKER,
)


def format_time_long(timestamp: datetime) -> str:
    """Time with seconds for the wide log, e.g. "12:34:56". The date is
    dropped."""
    return timestamp.strftime("%H:%M:%S")


class WidgetShipLogExtendedRow(HorizontalGroup):
    def __init__(self, entry: JournalLogViewModel, is_even_row: bool, **kwargs) -> None:
        """The entry category becomes a CSS class, so the marker and text get
        the category colour. Odd rows (is_even_row=False) get the "zebra-row"
        background."""
        super().__init__(classes=entry.category, **kwargs)
        self.entry = entry
        self.category = entry.category
        self.set_class(not is_even_row, "zebra-row")

    def compose(self) -> ComposeResult:
        """One label per column of the wide log header: time with seconds,
        category marker, event, system and details."""
        yield Label(format_time_long(self.entry.timestamp), classes="log-time")
        yield Label(CATEGORY_MARKER, classes="log-marker")
        yield Label(self.entry.event, classes="log-event")
        yield Label(self.entry.system, classes="log-system")
        yield Label(self.entry.details, classes="log-details")
