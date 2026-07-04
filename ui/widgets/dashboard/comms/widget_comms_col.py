from textual import log, on, work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label
from textual.reactive import reactive

from ui.widgets.dashboard.comms.widget_comms_entry import WidgetCommsEntry
from ui.widgets.dashboard.comms.widget_comms_input import WidgetCommsInput
from ui.widgets.dashboard.ed_dashboard_presenter import EdDashboardPresenter
from ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)


class WidgetCommsCol(Vertical):
    DEFAULT_CLASSES = "col"

    response_state: reactive[CommsMessageViewModel | None] = reactive(
        None, always_update=True
    )

    def __init__(self, ed_dashboard_presenter: EdDashboardPresenter, **kwargs) -> None:
        super().__init__(**kwargs)
        self.ed_dashboard_presenter = ed_dashboard_presenter

    def on_mount(self) -> None:
        self.set_up_stream_llm_responses_worker()

    def compose(self) -> ComposeResult:
        yield Label(content="COMMS")
        with VerticalScroll(id="comms-scroll"):
            yield WidgetCommsEntry(
                "system-message",
                "Welcome to EDCeleste! Type your command below to "
                "communicate with Celeste.",
            )

        yield WidgetCommsInput(self.ed_dashboard_presenter)

    def watch_response_state(self, new_state: CommsMessageViewModel | None) -> None:
        if new_state is not None:
            scroll_container = self.query_one("#comms-scroll", VerticalScroll)
            scroll_container.mount(
                WidgetCommsEntry(
                    "user-command" if new_state.is_user_message else "llm-response",
                    new_state.content,
                )
            )

    @work
    async def set_up_stream_llm_responses_worker(self) -> None:
        log.debug("Starting to stream LLM responses")
        async for response in self.ed_dashboard_presenter.stream_llm_responses():
            self.response_state = response

    @on(WidgetCommsInput.UserCommandSubmitted)
    def handle_user_command_submitted(
        self, event: WidgetCommsInput.UserCommandSubmitted
    ) -> None:
        log.debug("User command submitted: %s", event.command)
        self.response_state = CommsMessageViewModel.from_user_message(event.command)
