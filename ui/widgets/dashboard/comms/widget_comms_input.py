from textual import work, log
from textual.app import ComposeResult
from textual.widgets import Input
from textual.reactive import reactive
from textual.message import Message
from textual import on
from textual.containers import VerticalGroup

from services.models.llm_response import LLMStatus
from ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository


class WidgetCommsInput(VerticalGroup):
    llm_state: reactive[LLMStatus] = reactive(LLMStatus.IDLE)

    class UserCommandSubmitted(Message):
        def __init__(self, command: str) -> None:
            self.command = command
            super().__init__()

    def __init__(
        self, ed_dashboard_repository: EdDashboardRepository, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.ed_dashboard_repository = ed_dashboard_repository

    def on_mount(self) -> None:
        self.set_up_stream_llm_state_worker()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Input LLM command", id="comms-input", classes="input")

    def watch_llm_state(self, new_state: LLMStatus) -> None:
        log.debug("LLM state changed to: %s", new_state)

    @work
    async def set_up_stream_llm_state_worker(self) -> None:
        log.debug("Starting to stream LLM state")
        async for state in self.ed_dashboard_repository.stream_llm_state():
            log.debug("LLM state: %s", state)
            self.llm_state = state

    @on(Input.Submitted)
    @work
    async def handle_input_submitted(self, event: Input.Submitted) -> None:
        if not event.value.strip():
            log.debug("Ignoring empty command submission")
            return
        if self.llm_state == LLMStatus.IDLE:
            log.debug("Sending message to LLM: %s", event.value)
            self.post_message(self.UserCommandSubmitted(event.value))
            self.query_one("#comms-input", Input).value = ""
            await self.ed_dashboard_repository.send_message_to_llm(event.value)
        else:
            log.debug("LLM is busy, cannot send message: %s", event.value)
