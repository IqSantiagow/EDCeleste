import asyncio

from textual import work, log
from textual.app import ComposeResult
from textual.events import MouseDown, MouseEvent
from textual.widgets import Button, Input
from textual.reactive import reactive
from textual.message import Message
from textual import on
from textual.containers import HorizontalGroup, VerticalGroup

from edceleste.services.models.llm_status import LLMStatus
from edceleste.ui.widgets.common.widget_spinner import WidgetSpinner
from edceleste.ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository


class WidgetCommsInput(VerticalGroup):
    llm_state: reactive[LLMStatus] = reactive(LLMStatus.IDLE)

    stt_state: reactive[bool] = reactive(False)

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

    def compose(self) -> ComposeResult:
        with HorizontalGroup(classes="comms-input-container"):
            yield Input(placeholder="Input LLM command", id="comms-input")
            yield WidgetCommsInput.CommsSttButton()
        yield WidgetSpinner(
            "Celeste is thinking...", id="comms-thinking-indicator", classes="hidden"
        )

    def watch_llm_state(self, new_state: LLMStatus) -> None:
        log.debug("LLM state changed to: %s", new_state)
        indicator = self.query_one("#comms-thinking-indicator", WidgetSpinner)
        if new_state == LLMStatus.THINKING:
            indicator.remove_class("hidden")
            indicator.start()
        else:
            indicator.stop()
            indicator.add_class("hidden")

    @on(CommsSttButtonAction)
    @work
    async def on_comms_stt_button_action(self, message: CommsSttButtonAction) -> None:
        if message.is_up:
            log.debug("STT button released, stopping STT capture")
            result = None
            try:
                result = await asyncio.to_thread(
                    self.ed_dashboard_repository.stop_recording
                )
            except Exception as e:
                log.error("STT stop_recording failed: %s", e)
                self.notify(f"STT error: {e}", severity="error")
            finally:
                self.stt_state = False
            if result:
                self.query_one("#comms-input", Input).value = result
                await self.query_one("#comms-input", Input).action_submit()
        else:
            log.debug("STT button pressed, starting STT capture")
            try:
                self.ed_dashboard_repository.start_recording()
                self.stt_state = True
            except Exception as e:
                log.error("STT start_recording failed: %s", e)
                self.notify(f"STT error: {e}", severity="error")

    @on(Input.Submitted)
    def handle_input_submitted(self, event: Input.Submitted) -> None:
        if not event.value.strip():
            log.debug("Ignoring empty command submission")
            return

        log.debug("Queueing message for LLM: %s", event.value)
        self.post_message(self.UserCommandSubmitted(event.value))
        self.query_one("#comms-input", Input).value = ""
        self.ed_dashboard_repository.send_message_to_llm(event.value)

    def watch_stt_state(self, new_state: bool) -> None:
        if new_state:
            self.query_one("#comms-input", Input).disabled = True
            self.query_one("#comms-input", Input).placeholder = "Listening..."
        else:
            self.query_one("#comms-input", Input).disabled = False
            self.query_one("#comms-input", Input).placeholder = "Input LLM command"
