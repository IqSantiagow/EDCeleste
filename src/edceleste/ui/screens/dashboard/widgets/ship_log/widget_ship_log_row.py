from datetime import datetime

from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Label

from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    JournalLogViewModel,
)

CATEGORY_MARKER = "▌"


def format_time_short(timestamp: datetime) -> str:
    """12:34"""
    return timestamp.strftime("%H:%M")


def join_system_and_details(entry: JournalLogViewModel) -> str:
    if entry.system and entry.details:
        return f"{entry.system} · {entry.details}"
    return entry.system or entry.details


class WidgetShipLogRow(HorizontalGroup):
    def __init__(self, entry: JournalLogViewModel, **kwargs) -> None:
        super().__init__(classes=entry.category, **kwargs)
        self.entry = entry
        self.category = entry.category

    def compose(self) -> ComposeResult:
        yield Label(format_time_short(self.entry.timestamp), classes="log-time")
        yield Label(CATEGORY_MARKER, classes="log-marker")
        yield Label(self.entry.event, classes="log-event")
        yield Label(join_system_and_details(self.entry), classes="log-details")
