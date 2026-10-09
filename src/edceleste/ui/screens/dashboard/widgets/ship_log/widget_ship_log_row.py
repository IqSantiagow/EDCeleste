from datetime import datetime

from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label

from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    JournalLogViewModel,
)

CATEGORY_MARKER = "▌"


def format_time_short(timestamp: datetime) -> str:
    """Time without seconds for the narrow log, e.g. "12:34". The date is
    dropped."""
    return timestamp.strftime("%H:%M")


def join_system_and_details(entry: JournalLogViewModel) -> str:
    """The narrow log has no SYSTEM column, so the system goes in front of the
    details: "Sol · Docked". When one of them is empty only the other is shown,
    when both are empty the text is empty."""
    if entry.system and entry.details:
        return f"{entry.system} · {entry.details}"
    return entry.system or entry.details


class WidgetShipLogRow(HorizontalGroup):
    def __init__(self, entry: JournalLogViewModel, **kwargs) -> None:
        """The entry category becomes a CSS class, so the marker and text get
        the category colour."""
        super().__init__(classes=entry.category, **kwargs)
        self.entry = entry
        self.category = entry.category

    def compose(self) -> ComposeResult:
        """Short time (no seconds), category marker, event, and system joined
        with details in the last column."""
        yield Label(format_time_short(self.entry.timestamp), classes="log-time")
        yield Label(CATEGORY_MARKER, classes="log-marker")
        yield Label(self.entry.event, classes="log-event")
        yield Label(join_system_and_details(self.entry), classes="log-details")
