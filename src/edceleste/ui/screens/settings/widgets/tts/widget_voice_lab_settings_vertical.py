import enum

from dependency_injector.wiring import Provide, inject
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button

from edceleste.containers.main_container import Container
from edceleste.services.models.settings_model import TTSModel
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_slider_row import (
    WidgetLabeledSliderRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

VOICE_LAB_TEST_BUTTON_ID = "voice-lab-test-button"


class VoiceLabInputWidgetIds(enum.StrEnum):
    VOICE_LAB_ENABLED_INPUT = "voice-lab-enabled-input"
    VOICE_LAB_CLARITY_INPUT = "voice-lab-clarity-input"
    VOICE_LAB_REVERB_INPUT = "voice-lab-reverb-input"
    VOICE_LAB_STEREO_WIDTH_INPUT = "voice-lab-stereo-width-input"


class WidgetVoiceLabSettingsVertical(Vertical):
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
        place when a value changes (the widget posts ValueChanged and never
        writes). The test button reads the whole tts_model when it is pressed,
        so it plays what is on the screen now, saved or not. settings_repository
        is the only thing the widget calls: the test button's worker uses its
        play_voice_lab_test() to speak the sentence. It is injected when not
        given, because this module is listed in MODULES_USING_PROVIDE. *args
        and **kwargs go to Vertical."""
        super().__init__(*args, **kwargs)
        self.tts_model = tts_model
        self.settings_repository = settings_repository

    def compose(self) -> ComposeResult:
        voice_lab = self.tts_model.voice_lab
        yield WidgetSectionHeader("VOICE LAB")
        yield WidgetLabeledSwitchRow(
            "Voice effects:",
            voice_lab.enabled,
            hint="sounds like inside the ship",
            id=VoiceLabInputWidgetIds.VOICE_LAB_ENABLED_INPUT,
        )
        sliders = {
            "Clarity:": (
                voice_lab.clarity,
                VoiceLabInputWidgetIds.VOICE_LAB_CLARITY_INPUT,
            ),
            "Reverb:": (
                voice_lab.reverb,
                VoiceLabInputWidgetIds.VOICE_LAB_REVERB_INPUT,
            ),
            "Stereo width:": (
                voice_lab.stereo_width,
                VoiceLabInputWidgetIds.VOICE_LAB_STEREO_WIDTH_INPUT,
            ),
        }
        for label, (value, widget_id) in sliders.items():
            yield WidgetLabeledSliderRow(
                label, 0, 1, value, step=0.05, id=widget_id, classes="voice-lab-slider"
            )
        yield WidgetButton("▶ Test voice", id=VOICE_LAB_TEST_BUTTON_ID)

    def on_mount(self) -> None:
        self.set_sliders_visible(self.tts_model.voice_lab.enabled)

    def on_value_changed(self, message: ValueChanged) -> None:
        if message.sender_id == VoiceLabInputWidgetIds.VOICE_LAB_ENABLED_INPUT:
            self.set_sliders_visible(message.new_value)

    def set_sliders_visible(self, visible: bool) -> None:
        """Shows the three slider rows when visible is True and hides them when
        it is False, by setting display on every row with the
        "voice-lab-slider" class. The switch row and the test button are not
        touched. Hidden sliders keep their values, they are only not
        displayed."""
        for slider_row in self.query(".voice-lab-slider"):
            slider_row.display = visible

    @on(Button.Pressed, f"#{VOICE_LAB_TEST_BUTTON_ID}")
    def handle_test_pressed(self, event: Button.Pressed) -> None:
        """Runs when the test button is pressed. Starts the worker
        play_voice_lab_test_sentence_in_background() with the pressed button
        and returns at once, so the UI does not wait for the sound. The
        button is disabled by the worker, not here."""
        self.play_voice_lab_test_sentence_in_background(event.button)

    @work
    async def play_voice_lab_test_sentence_in_background(
        self, test_button: Button
    ) -> None:
        """Worker. Speaks the test sentence through the speakers with
        self.tts_model, the TTS settings on the screen at the moment the
        worker runs (engine, volume, Voice Lab switch and sliders).

        The button is disabled until the sound ends, so a second press cannot
        start a second sentence while the first is still being made (Chatterbox
        needs a few seconds for it). Any error, e.g. no voice picked, no
        network or a deleted profile, is logged and shown as an error
        notification "Voice test failed: <error>", and the button works again.
        Nothing is raised and nothing is saved. Leaving the screen cancels the
        worker and enables the button again, the sound already handed to the
        speakers plays to the end.
        """
        test_button.disabled = True
        try:
            await self.settings_repository.play_voice_lab_test(self.tts_model)
        except Exception as error:
            self.log(f"Voice Lab test failed: {error!r}")
            self.notify(f"Voice test failed: {error}", severity="error")
        finally:
            test_button.disabled = False
