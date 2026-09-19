from textual import on
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Rule, TabbedContent, TabPane

from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    JournalLogViewModel,
    format_thousands,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.ship_log_tabs import (
    SHIP_LOG_TAB_LOG,
    SHIP_LOG_TAB_STATION,
    compose_placeholder_tab_panes,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_station_market import (
    WidgetStationMarket,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_extended_row import (  # noqa: E501
    WidgetShipLogExtendedRow,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_filter_bar import (
    FILTER_ALL,
    WidgetShipLogFilterBar,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_panel import (
    MAX_ROWS,
)

SCROLL_ID = "ship-log-extended-scroll"


class WidgetShipLogExtendedPanel(Widget):
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
                with HorizontalGroup(classes="ship-log-header-row"):
                    yield Label("TIME", classes="log-time")
                    yield Label(" ", classes="log-marker")
                    yield Label("EVENT", classes="log-event")
                    yield Label("SYSTEM", classes="log-system")
                    yield Label("DETAILS", classes="log-details")
                yield Rule(classes="ship-log-header-divider")
                yield VerticalScroll(id=SCROLL_ID)
            yield from compose_placeholder_tab_panes(
                {SHIP_LOG_TAB_STATION: WidgetStationMarket()}
            )

    def on_mount(self) -> None:
        self.call_after_refresh(self.rebuild_rows)

    def add_entry(self, entry: JournalLogViewModel) -> None:
        self.entries.append(entry)
        self.total_events_count += 1
        self.border_subtitle = (
            f"{format_thousands(self.total_events_count)} events this session"
        )
        if self.matches_active_filter(entry):
            self.mount_row(entry)
        self.drop_oldest_entry_over_limit()

    def matches_active_filter(self, entry: JournalLogViewModel) -> bool:
        return self.active_filter == FILTER_ALL or entry.category == self.active_filter

    def mount_row(self, entry: JournalLogViewModel) -> None:
        scroll = self.query_one(f"#{SCROLL_ID}", VerticalScroll)
        is_even_row = len(scroll.children) % 2 == 0
        scroll.mount(WidgetShipLogExtendedRow(entry, is_even_row))
        scroll.scroll_end(animate=False)

    def rebuild_rows(self) -> None:
        self.query_one(f"#{SCROLL_ID}", VerticalScroll).remove_children()
        for entry in self.entries:
            if self.matches_active_filter(entry):
                self.mount_row(entry)

    def drop_oldest_entry_over_limit(self) -> None:
        if len(self.entries) <= MAX_ROWS:
            return
        oldest_entry = self.entries.pop(0)
        if self.matches_active_filter(oldest_entry):
            self.query(WidgetShipLogExtendedRow).first().remove()

    @on(WidgetShipLogFilterBar.FilterSelected)
    def handle_filter_selected(
        self, message: WidgetShipLogFilterBar.FilterSelected
    ) -> None:
        self.active_filter = message.filter_value
        self.rebuild_rows()
