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
        """Only reads tts_model, the screen's working copy of the TTS settings
        (WidgetTTSContainer changes it in place). The changes go up as
        ValueChanged and WidgetTTSContainer writes them. The test button reads
        the whole tts_model when it is pressed, so it plays what is on the
        screen now, saved or not."""
        super().__init__(*args, **kwargs)
        self.tts_model = tts_model
        self.settings_repository = settings_repository

    def compose(self) -> ComposeResult:
        """The on/off switch, three 0.0-1.0 sliders (clarity, reverb, stereo
        width) and the test button. The sliders get the "voice-lab-slider"
        class, so show_sliders() can find them. The button stays visible when
        the effects are off, it then plays the plain voice."""
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
        """Hides the sliders at the start when the effects are off."""
        self.show_sliders(self.tts_model.voice_lab.enabled)

    def on_value_changed(self, message: ValueChanged) -> None:
        """Shows or hides the sliders when the switch flips. It does not stop
        the message, WidgetTTSContainer still gets it and writes the
        values."""
        if message.sender_id == VoiceLabInputWidgetIds.VOICE_LAB_ENABLED_INPUT:
            self.show_sliders(message.new_value)

    def show_sliders(self, visible: bool) -> None:
        """Hidden sliders keep their values, they are only not displayed."""
        for slider_row in self.query(".voice-lab-slider"):
            slider_row.display = visible

    @on(Button.Pressed, f"#{VOICE_LAB_TEST_BUTTON_ID}")
    def handle_test_pressed(self, event: Button.Pressed) -> None:
        """The test button. Playing runs in a worker, so the UI does not wait
        for the sound."""
        self.play_test_sentence(event.button)

    @work
    async def play_test_sentence(self, test_button: Button) -> None:
        """Worker. Speaks the test sentence with the TTS settings from the
        screen and the Voice Lab effects from the sliders, through the
        speakers.

        The button is disabled until the sound ends, so a second press cannot
        start a second sentence while the first is still being made (Chatterbox
        needs a few seconds for it). Any error, e.g. no voice picked, no
        network or a deleted profile, is shown as a notification and the button
        works again.
        """
        test_button.disabled = True
        try:
            await self.settings_repository.play_voice_lab_test(self.tts_model)
        except Exception as error:
            self.log(f"Voice Lab test failed: {error!r}")
            self.notify(f"Voice test failed: {error}", severity="error")
        finally:
            test_button.disabled = False
