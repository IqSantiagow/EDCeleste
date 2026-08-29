from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.reactive import reactive

from edceleste.ui.widgets.dashboard.comms.widget_comms_entry import WidgetCommsEntry
from edceleste.ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)


class WidgetCommsCol(Vertical):
    response_state: reactive[CommsMessageViewModel | None] = reactive(
        None, always_update=True
    )

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="comms-scroll"):
            yield WidgetCommsEntry(
                "system-message",
                "Welcome to EDCeleste! Type your command below to "
                "communicate with Celeste.",
            )

    def watch_response_state(self, new_state: CommsMessageViewModel | None) -> None:
        if new_state is None:
            return

        self.query_one("#comms-scroll", VerticalScroll).mount(
            WidgetCommsEntry(new_state.entry_type, new_state.content)
        )
