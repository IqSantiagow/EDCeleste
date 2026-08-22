from textual import work, log
from textual.app import ComposeResult
from textual.events import MouseDown, MouseEvent
from textual.timer import Timer
from textual.widgets import Button, Input, Static
from textual.reactive import reactive
from textual.message import Message
from textual import on
from textual.containers import HorizontalGroup, VerticalGroup

from services.models.llm_response import LLMStatus
from ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository


class WidgetCommsInput(VerticalGroup):
    llm_state: reactive[LLMStatus] = reactive(LLMStatus.IDLE)

    stt_state: reactive[bool] = reactive(False)

    SPINNER_FRAMES = [
        "\u280b",
        "\u2819",
        "\u2839",
        "\u2838",
        "\u283c",
        "\u2834",
        "\u2826",
        "\u2827",
        "\u2807",
        "\u280f",
    ]

    class CommsSttButtonAction(Message):
        def __init__(self, is_up: bool) -> None:
            self.is_up = is_up
            super().__init__()

    class CommsSttButton(Button):
        def __init__(self, **kwargs) -> None:
            super().__init__("[🎤]", id="comms-stt-button", flat=True, **kwargs)

        def on_mouse_down(self, event: MouseDown) -> None:
            self.capture_mouse(capture=True)
            log.debug("STT button pressed, starting STT capture")
            self.post_message(WidgetCommsInput.CommsSttButtonAction(is_up=False))

        def on_mouse_up(self, event: MouseEvent) -> None:
            self.release_mouse()
            log.debug("STT button released, stopping STT capture")
            self.post_message(WidgetCommsInput.CommsSttButtonAction(is_up=True))

    class UserCommandSubmitted(Message):
        def __init__(self, command: str) -> None:
            self.command = command
            super().__init__()

    def __init__(
        self, ed_dashboard_repository: EdDashboardRepository, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.ed_dashboard_repository = ed_dashboard_repository
        self._spinner_index = 0
        self._spinner_timer: Timer | None = None

    def on_mount(self) -> None:
        self.set_up_stream_llm_state_worker()

    def compose(self) -> ComposeResult:
        with HorizontalGroup(classes="comms-input-container"):
            yield Input(placeholder="Input LLM command", id="comms-input")
            yield WidgetCommsInput.CommsSttButton()
        yield Static("", id="comms-thinking-indicator", classes="hidden")

    def watch_llm_state(self, new_state: LLMStatus) -> None:
        log.debug("LLM state changed to: %s", new_state)
        if new_state == LLMStatus.THINKING:
            self._start_thinking_animation()
        else:
            self._stop_thinking_animation()

    def _start_thinking_animation(self) -> None:
        if self._spinner_timer is not None:
            return
        indicator = self.query_one("#comms-thinking-indicator", Static)
        indicator.remove_class("hidden")
        self._spinner_index = 0
        self._spinner_timer = self.set_interval(0.1, self._advance_spinner)

    def _stop_thinking_animation(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        indicator = self.query_one("#comms-thinking-indicator", Static)
        indicator.add_class("hidden")
        indicator.update("")

    def _advance_spinner(self) -> None:
        frame = self.SPINNER_FRAMES[self._spinner_index % len(self.SPINNER_FRAMES)]
        self._spinner_index += 1
        self.query_one("#comms-thinking-indicator", Static).update(
            f"{frame} Celeste is thinking..."
        )

    @on(CommsSttButtonAction)
    @work
    async def on_comms_stt_button_action(self, message: CommsSttButtonAction) -> None:
        if message.is_up:
            log.debug("STT button released, stopping STT capture")
            result = self.ed_dashboard_repository.stop_recording()
            self.stt_state = False
            if result:
                self.query_one("#comms-input", Input).value = result
                await self.query_one("#comms-input", Input).action_submit()
        else:
            log.debug("STT button pressed, starting STT capture")
            self.ed_dashboard_repository.start_recording()
            self.stt_state = True

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

    def watch_stt_state(self, new_state: bool) -> None:
        if new_state:
            self.query_one("#comms-input", Input).disabled = True
            self.query_one("#comms-input", Input).placeholder = "Listening..."
        else:
            self.query_one("#comms-input", Input).disabled = False
            self.query_one("#comms-input", Input).placeholder = "Input LLM command"
