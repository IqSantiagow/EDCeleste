from textual import on
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import TabbedContent, TabPane

from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    JournalLogViewModel,
    format_thousands,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.ship_log_tabs import (
    SHIP_LOG_TAB_LOG,
    compose_placeholder_tab_panes,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_filter_bar import (
    FILTER_ALL,
    WidgetShipLogFilterBar,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_row import (
    WidgetShipLogRow,
)

# How many rows we keep in memory. The event counter keeps growing regardless.
MAX_ROWS = 200


class WidgetShipLogPanel(Widget):
    DEFAULT_CLASSES = "titled-panel"
    BORDER_TITLE = "SHIP LOG"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.entries: list[JournalLogViewModel] = []
        self.total_events_count = 0
        self.active_filter = FILTER_ALL

    def compose(self) -> ComposeResult:
        with TabbedContent(initial=SHIP_LOG_TAB_LOG):
            with TabPane("LOG", id=SHIP_LOG_TAB_LOG):
                yield WidgetShipLogFilterBar()
                yield VerticalScroll(id="ship-log-scroll")
            yield from compose_placeholder_tab_panes()

    def on_mount(self) -> None:
        self.call_after_refresh(self.rebuild_rows)

    def add_entry(self, entry: JournalLogViewModel) -> None:
        self.entries.append(entry)
        self.total_events_count += 1
        self.border_subtitle = f"{format_thousands(self.total_events_count)} events"
        if self.matches_active_filter(entry):
            self.mount_row(entry)
        self.drop_oldest_entry_over_limit()

    def matches_active_filter(self, entry: JournalLogViewModel) -> bool:
        return self.active_filter == FILTER_ALL or entry.category == self.active_filter

    def mount_row(self, entry: JournalLogViewModel) -> None:
        scroll = self.query_one("#ship-log-scroll", VerticalScroll)
        scroll.mount(WidgetShipLogRow(entry))
        scroll.scroll_end(animate=False)

    def rebuild_rows(self) -> None:
        self.query_one("#ship-log-scroll", VerticalScroll).remove_children()
        for entry in self.entries:
            if self.matches_active_filter(entry):
                self.mount_row(entry)

    def drop_oldest_entry_over_limit(self) -> None:
        if len(self.entries) <= MAX_ROWS:
            return
        oldest_entry = self.entries.pop(0)
        if self.matches_active_filter(oldest_entry):
            self.query(WidgetShipLogRow).first().remove()

    @on(WidgetShipLogFilterBar.FilterSelected)
    def handle_filter_selected(
        self, message: WidgetShipLogFilterBar.FilterSelected
    ) -> None:
        self.active_filter = message.filter_value
        self.rebuild_rows()
