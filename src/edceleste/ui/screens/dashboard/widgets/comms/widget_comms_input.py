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
from edceleste.ui.screens.dashboard.ed_dashboard_repository import EdDashboardRepository


class WidgetCommsInput(VerticalGroup):
    llm_state: reactive[LLMStatus] = reactive(LLMStatus.IDLE)

    stt_state: reactive[bool] = reactive(False)

    class CommsSttButtonAction(Message):
        def __init__(self, is_up: bool) -> None:
            """is_up=False means the mic button went down (start recording),
            is_up=True means it was released (stop and transcribe)."""
            self.is_up = is_up
            super().__init__()

    class CommsSttButton(Button):
        def __init__(self, **kwargs) -> None:
            """Push to talk mic button. It does not use Button.Pressed, it
            reacts to mouse down and mouse up on its own."""
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
            """Bubbles up to the dashboard screen, which shows the command as a
            "YOU:" line in COMMS."""
            self.command = command
            super().__init__()

    def __init__(
        self, ed_dashboard_repository: EdDashboardRepository, **kwargs
    ) -> None:
        """Only stores the repository. Recording and sending pilot messages go
        through it."""
        super().__init__(**kwargs)
        self.ed_dashboard_repository = ed_dashboard_repository

    def on_mount(self) -> None:
        self.send_spoken_commands()

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
            try:
                await asyncio.to_thread(
                    self.ed_dashboard_repository.stop_recording_and_transcribe
                )
            except Exception as e:
                log.error("STT stop_recording_and_transcribe failed: %s", e)
                self.notify(f"STT error: {e}", severity="error")
            finally:
                self.stt_state = False
        else:
            log.debug("STT button pressed, starting STT capture")
            try:
                self.ed_dashboard_repository.start_recording()
                self.stt_state = True
            except Exception as e:
                log.error("STT start_recording failed: %s", e)
                self.notify(f"STT error: {e}", severity="error")

    @work
    async def send_spoken_commands(self) -> None:
        """Worker that never ends and is the only reader of the STT queue.
        Every text that comes out of it, from the mic button or from the
        hotkey, is put in the input and submitted, so it takes the same way as
        a typed message."""
        stream = self.ed_dashboard_repository.stream_stt_transcriptions()
        async for spoken_text in stream:
            self.query_one("#comms-input", Input).value = spoken_text
            await self.query_one("#comms-input", Input).action_submit()

    @on(Input.Submitted)
    def send_pilot_message_from_input(self, event: Input.Submitted) -> None:
        """Runs on Enter in the input and after a voice command is put in it, so
        typed and spoken messages take the same way. The text is sent as it is,
        not trimmed.

        1. Blank or whitespace only text is ignored.
        2. Posts UserCommandSubmitted, so the dashboard shows the "YOU:" line.
        3. Clears the input.
        4. Sends the message on (Instinct or the LLM queue). It does not wait
           for the reply, the reply comes back through the dashboard's LLM
           stream. Needs the app event loop.
        """
        if not event.value.strip():
            log.debug("Ignoring empty command submission")
            return

        log.debug("Sending the pilot message: %s", event.value)
        self.post_message(self.UserCommandSubmitted(event.value))
        self.query_one("#comms-input", Input).value = ""
        self.ed_dashboard_repository.send_pilot_message(event.value)

    def watch_stt_state(self, new_state: bool) -> None:
        if new_state:
            self.query_one("#comms-input", Input).disabled = True
            self.query_one("#comms-input", Input).placeholder = "Listening..."
        else:
            self.query_one("#comms-input", Input).disabled = False
            self.query_one("#comms-input", Input).placeholder = "Input LLM command"
