from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Label
from textual.reactive import reactive

from ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository
from ui.widgets.dashboard.ship_log.widget_ship_log_entry import WidgetShipLogEntry
from ui.widgets.dashboard.view_models.journal_log_view_model import JournalLogViewModel


def format_timestamp(timestamp: str) -> str:
    """return only hours, minutes from timestamp"""
    return timestamp.split(" ")[1][:5]


class WidgetShipLogCol(Widget):
    old_state: list[JournalLogViewModel] = []
    state: reactive[list[JournalLogViewModel]] = reactive([])

    def __init__(
        self, ed_dashboard_repository: EdDashboardRepository, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.state = []
        self.old_state = []
        self.ed_dashboard_repository = ed_dashboard_repository

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="ship-log-scroll"):
            for event in self.state:
                yield Label(
                    content=f"{event.timestamp} - {event.event} - {event.details}"
                )

    def on_mount(self) -> None:
        self.set_up_stream_journal_worker()

    def watch_state(self, new_state: list[JournalLogViewModel]) -> None:
        new_events = [event for event in new_state if event not in self.old_state]
        for event in new_events:
            self.query_one("#ship-log-scroll", VerticalScroll).mount(
                WidgetShipLogEntry(
                    timestamp=format_timestamp(event.timestamp),
                    event=event.event,
                    details=event.details,
                )
            )
        self.old_state = list(new_state)

    @work(exclusive=True)
    async def set_up_stream_journal_worker(self) -> None:
        async for event in self.ed_dashboard_repository.stream_journal_events():
            self.state.append(event)
            self.mutate_reactive(WidgetShipLogCol.state)
