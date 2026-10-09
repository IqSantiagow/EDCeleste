from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.reactive import reactive

from edceleste.ui.screens.dashboard.widgets.comms.widget_comms_entry import (
    WidgetCommsEntry,
)
from edceleste.ui.screens.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)


class WidgetCommsCol(Vertical):
    DEFAULT_CLASSES = "titled-panel"
    BORDER_TITLE = "COMMS"

    # always_update: two identical messages in a row must both show up.
    response_state: reactive[CommsMessageViewModel | None] = reactive(
        None, always_update=True
    )

    def compose(self) -> ComposeResult:
        """Starts the chat with one SYSTEM welcome line. New lines are added
        later by watch_response_state()."""
        with VerticalScroll(id="comms-scroll"):
            yield WidgetCommsEntry(
                "system-message",
                "Welcome to EDCeleste! Type your command below to "
                "communicate with Celeste.",
            )

    def watch_response_state(self, new_state: CommsMessageViewModel | None) -> None:
        """Runs every time the dashboard screen sets response_state, for the
        pilot's own command and for every reply block from the LLM. Mounts one
        new WidgetCommsEntry at the bottom of the chat. Old lines are never
        removed. None does nothing."""
        if new_state is None:
            return

        self.query_one("#comms-scroll", VerticalScroll).mount(
            WidgetCommsEntry(new_state.entry_type, new_state.content)
        )
