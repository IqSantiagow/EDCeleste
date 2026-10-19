from dependency_injector.wiring import Provide, inject
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button

from edceleste.containers.main_container import Container
from edceleste.services.models.settings_model import TTSModel
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton

VOICE_TEST_BUTTON_ID = "voice-test-button"


class WidgetVoiceTestButton(Vertical):
    @inject
    def __init__(
        self,
        tts_model: TTSModel,
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        *args,
        **kwargs,
    ) -> None:
        """Only stores tts_model and settings_repository, nothing is read or
        played here. tts_model is kept as it is, not copied: it is the screen's
        working copy of the TTS settings, and WidgetTTSContainer changes it in
        place when a value changes. The button reads the whole tts_model when it
        is pressed, so it plays what is on the screen now, saved or not.
        settings_repository is the only thing the widget calls: the worker uses
        its play_voice_test() to speak the sentence. It is injected when not
        given, because this module is listed in MODULES_USING_PROVIDE. *args
        and **kwargs go to Vertical."""
        super().__init__(*args, **kwargs)
        self.tts_model = tts_model
        self.settings_repository = settings_repository

    def compose(self) -> ComposeResult:
        yield WidgetButton("▶ Test voice", id=VOICE_TEST_BUTTON_ID)

    @on(Button.Pressed, f"#{VOICE_TEST_BUTTON_ID}")
    def handle_test_pressed(self, event: Button.Pressed) -> None:
        """Runs when the test button is pressed. Does nothing when the button is
        already disabled: a second press that was queued before the first one
        was handled must not start a second sentence. Otherwise disables the
        button at once, then starts the worker
        play_voice_test_sentence_in_background() with the button and returns,
        so the UI does not wait for the sound. The worker enables the button
        again."""
        if event.button.disabled:
            return
        event.button.disabled = True
        self.play_voice_test_sentence_in_background(event.button)

    @work
    async def play_voice_test_sentence_in_background(self, test_button: Button) -> None:
        """Worker. Speaks the test sentence through the speakers with
        self.tts_model, the TTS settings on the screen at the moment the worker
        runs (engine, volume and the ship effect switch).

        The button was disabled by handle_test_pressed() and stays disabled
        until the sound ends, so a second press cannot start a second sentence
        while the first is still being made (Chatterbox and Pocket TTS need a
        few seconds for it). Any error, e.g. no voice picked, no network or a
        deleted profile, is logged and shown as an error notification "Voice
        test failed: <error>", and the button works again. Nothing is raised
        and nothing is saved. Leaving the screen cancels the worker and enables
        the button again, the sound already handed to the speakers plays to the
        end.
        """
        try:
            await self.settings_repository.play_voice_test(self.tts_model)
        except Exception as error:
            self.log(f"Voice test failed: {error!r}")
            self.notify(f"Voice test failed: {error}", severity="error")
        finally:
            test_button.disabled = False
