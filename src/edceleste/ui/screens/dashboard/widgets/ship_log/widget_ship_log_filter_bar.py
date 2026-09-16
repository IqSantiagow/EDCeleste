from textual import events, on
from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.message import Message
from textual.widgets import Label

from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    CATEGORY_COMBAT,
    CATEGORY_NAV,
    CATEGORY_TOOLS,
)

# An empty value means "show everything".
FILTER_ALL = ""

SHIP_LOG_FILTERS = (
    ("ALL", FILTER_ALL),
    ("NAV", CATEGORY_NAV),
    ("COMBAT", CATEGORY_COMBAT),
    ("TOOLS", CATEGORY_TOOLS),
)


class WidgetShipLogFilterChip(Label):
    def __init__(self, label: str, filter_value: str, **kwargs) -> None:
        super().__init__(label, **kwargs)
        self.filter_value = filter_value

    def on_click(self, _: events.Click) -> None:
        self.post_message(WidgetShipLogFilterBar.FilterSelected(self.filter_value))


class WidgetShipLogFilterBar(HorizontalGroup):
    class FilterSelected(Message):
        def __init__(self, filter_value: str) -> None:
            self.filter_value = filter_value
            super().__init__()

    def compose(self) -> ComposeResult:
        for label, filter_value in SHIP_LOG_FILTERS:
            chip = WidgetShipLogFilterChip(label, filter_value)
            if filter_value == FILTER_ALL:
                chip.add_class("-active")
            yield chip

    @on(FilterSelected)
    def highlight_selected_chip(self, message: FilterSelected) -> None:
        """Highlight the clicked chip. The message keeps bubbling up to the panel."""
        for chip in self.query(WidgetShipLogFilterChip):
            chip.set_class(chip.filter_value == message.filter_value, "-active")
