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
        """Starts with no entries, a zero event counter and the ALL filter."""
        super().__init__(**kwargs)
        self.entries: list[JournalLogViewModel] = []
        self.total_events_count = 0
        self.active_filter = FILTER_ALL

    def compose(self) -> ComposeResult:
        """The narrow ship log: a LOG tab with the filter bar and an empty
        scroll for the rows, then the other cockpit cards as "NO DATA"
        placeholders. Rows are mounted later by add_entry()."""
        with TabbedContent(initial=SHIP_LOG_TAB_LOG):
            with TabPane("LOG", id=SHIP_LOG_TAB_LOG):
                yield WidgetShipLogFilterBar()
                yield VerticalScroll(id="ship-log-scroll")
            yield from compose_placeholder_tab_panes()

    def on_mount(self) -> None:
        """Waits for the first refresh, then mounts rows for entries that
        arrived before the panel was ready."""
        self.call_after_refresh(self.rebuild_rows)

    def add_entry(self, entry: JournalLogViewModel) -> None:
        """Called by the dashboard screen for every new journal event.

        1. Remembers the entry and counts it.
        2. Shows the count as "<n> events" in the border subtitle.
        3. Mounts a row only when the entry passes the active filter.
        4. Drops the oldest entry when there are more than MAX_ROWS.
        """
        self.entries.append(entry)
        self.total_events_count += 1
        self.border_subtitle = f"{format_thousands(self.total_events_count)} events"
        if self.matches_active_filter(entry):
            self.mount_row(entry)
        self.drop_oldest_entry_over_limit()

    def matches_active_filter(self, entry: JournalLogViewModel) -> bool:
        """The ALL filter lets every entry in, any other filter only entries of
        the same category."""
        return self.active_filter == FILTER_ALL or entry.category == self.active_filter

    def mount_row(self, entry: JournalLogViewModel) -> None:
        """Adds the row at the bottom and scrolls down to it at once."""
        scroll = self.query_one("#ship-log-scroll", VerticalScroll)
        scroll.mount(WidgetShipLogRow(entry))
        scroll.scroll_end(animate=False)

    def rebuild_rows(self) -> None:
        """Removes every row and mounts again the remembered entries that pass
        the active filter, oldest first."""
        self.query_one("#ship-log-scroll", VerticalScroll).remove_children()
        for entry in self.entries:
            if self.matches_active_filter(entry):
                self.mount_row(entry)

    def drop_oldest_entry_over_limit(self) -> None:
        """Does nothing up to MAX_ROWS entries. Above it forgets the oldest
        entry and removes the top row, but only if that entry was shown under
        the active filter. The event counter is not lowered."""
        if len(self.entries) <= MAX_ROWS:
            return
        oldest_entry = self.entries.pop(0)
        if self.matches_active_filter(oldest_entry):
            self.query(WidgetShipLogRow).first().remove()

    @on(WidgetShipLogFilterBar.FilterSelected)
    def show_only_rows_of_selected_filter(
        self, message: WidgetShipLogFilterBar.FilterSelected
    ) -> None:
        """Runs when the pilot clicks a filter chip. Stores the new filter and
        rebuilds all rows from the remembered entries."""
        self.active_filter = message.filter_value
        self.rebuild_rows()
