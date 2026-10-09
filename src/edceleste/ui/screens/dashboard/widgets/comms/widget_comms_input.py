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
            """Captures the mouse, so the release is caught even when the
            pointer has left the button, and posts
            CommsSttButtonAction(is_up=False) to WidgetCommsInput."""
            self.capture_mouse(capture=True)
            log.debug("STT button pressed, starting STT capture")
            self.post_message(WidgetCommsInput.CommsSttButtonAction(is_up=False))

        def on_mouse_up(self, event: MouseEvent) -> None:
            """Releases the mouse capture and posts
            CommsSttButtonAction(is_up=True) to WidgetCommsInput."""
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
        """Only stores the repository. Recording and sending to the LLM go
        through it."""
        super().__init__(**kwargs)
        self.ed_dashboard_repository = ed_dashboard_repository

    def compose(self) -> ComposeResult:
        """The text input with the mic button next to it, and below them a
        hidden "Celeste is thinking..." spinner that watch_llm_state() shows."""
        with HorizontalGroup(classes="comms-input-container"):
            yield Input(placeholder="Input LLM command", id="comms-input")
            yield WidgetCommsInput.CommsSttButton()
        yield WidgetSpinner(
            "Celeste is thinking...", id="comms-thinking-indicator", classes="hidden"
        )

    def watch_llm_state(self, new_state: LLMStatus) -> None:
        """Runs when the dashboard screen sets llm_state from the LLM stream.
        THINKING shows and starts the spinner, any other status stops and hides
        it. The input stays usable while Celeste thinks."""
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
        """Push to talk, runs as a Textual worker.

        Button down (is_up=False):
        1. Starts recording from the microphone.
        2. Sets stt_state=True, which locks the input (watch_stt_state).

        Button up (is_up=True):
        1. Stops recording and transcribes the audio in a thread, because
           Whisper blocks.
        2. Sets stt_state=False in every case, so the input is unlocked again.
        3. If there is text, puts it in the input and submits it, so it goes
           the same way as a typed command (send_typed_command_to_llm).
           No text (None or empty) sends nothing.

        Any error (STT disabled, already recording, nothing recorded) is shown
        as an error toast and logged, never raised.
        """
        if message.is_up:
            log.debug("STT button released, stopping STT capture")
            result = None
            try:
                result = await asyncio.to_thread(
                    self.ed_dashboard_repository.stop_recording_and_transcribe
                )
            except Exception as e:
                log.error("STT stop_recording_and_transcribe failed: %s", e)
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
    def send_typed_command_to_llm(self, event: Input.Submitted) -> None:
        """Runs on Enter in the input and after a voice command is put in it.

        1. Blank or whitespace only text is ignored.
        2. Posts UserCommandSubmitted, so the dashboard shows the "YOU:" line.
        3. Clears the input.
        4. Puts the command in the LLM queue. It does not wait for the reply,
           the reply comes back through the dashboard's LLM stream.
        """
        if not event.value.strip():
            log.debug("Ignoring empty command submission")
            return

        log.debug("Queueing message for LLM: %s", event.value)
        self.post_message(self.UserCommandSubmitted(event.value))
        self.query_one("#comms-input", Input).value = ""
        self.ed_dashboard_repository.send_message_to_llm(event.value)

    def watch_stt_state(self, new_state: bool) -> None:
        """While recording (True) the input is disabled and says
        "Listening...", so the pilot cannot type over the voice command. False
        brings back the normal input."""
        if new_state:
            self.query_one("#comms-input", Input).disabled = True
            self.query_one("#comms-input", Input).placeholder = "Listening..."
        else:
            self.query_one("#comms-input", Input).disabled = False
            self.query_one("#comms-input", Input).placeholder = "Input LLM command"
