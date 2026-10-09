import enum

from textual.app import ComposeResult
from textual.containers import Vertical

from edceleste.services.models.settings_model import VoiceLabModel
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_slider_row import (
    WidgetLabeledSliderRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


class VoiceLabInputWidgetIds(enum.StrEnum):
    VOICE_LAB_ENABLED_INPUT = "voice-lab-enabled-input"
    VOICE_LAB_CLARITY_INPUT = "voice-lab-clarity-input"
    VOICE_LAB_REVERB_INPUT = "voice-lab-reverb-input"
    VOICE_LAB_STEREO_WIDTH_INPUT = "voice-lab-stereo-width-input"


class WidgetVoiceLabSettingsVertical(Vertical):
    def __init__(self, voice_lab: VoiceLabModel, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.voice_lab = voice_lab

    def compose(self) -> ComposeResult:
        yield WidgetSectionHeader("VOICE LAB")
        yield WidgetLabeledSwitchRow(
            "Voice effects:",
            self.voice_lab.enabled,
            hint="sounds like inside the ship",
            id=VoiceLabInputWidgetIds.VOICE_LAB_ENABLED_INPUT,
        )
        sliders = {
            "Clarity:": (
                self.voice_lab.clarity,
                VoiceLabInputWidgetIds.VOICE_LAB_CLARITY_INPUT,
            ),
            "Reverb:": (
                self.voice_lab.reverb,
                VoiceLabInputWidgetIds.VOICE_LAB_REVERB_INPUT,
            ),
            "Stereo width:": (
                self.voice_lab.stereo_width,
                VoiceLabInputWidgetIds.VOICE_LAB_STEREO_WIDTH_INPUT,
            ),
        }
        for label, (value, widget_id) in sliders.items():
            yield WidgetLabeledSliderRow(
                label, 0, 1, value, step=0.05, id=widget_id, classes="voice-lab-slider"
            )

    def on_mount(self) -> None:
        self.show_sliders(self.voice_lab.enabled)

    def on_value_changed(self, message: ValueChanged) -> None:
        if message.sender_id == VoiceLabInputWidgetIds.VOICE_LAB_ENABLED_INPUT:
            self.show_sliders(message.new_value)

    def show_sliders(self, visible: bool) -> None:
        for slider_row in self.query(".voice-lab-slider"):
            slider_row.display = visible
