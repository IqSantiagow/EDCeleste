import enum

from textual.containers import Vertical
from textual.app import ComposeResult

from edceleste.services.models.settings_model import ChatterboxParamsModel
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_slider_row import (
    WidgetLabeledSliderRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.screens.settings.widgets.tts.widget_voice_profiles_vertical import (
    WidgetVoiceProfilesVertical,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

CHATTERBOX_DEVICE_OPTIONS = ["auto", "cuda", "cpu"]


class ChatterboxTTSInputWidgetIds(enum.StrEnum):
    TTS_EXAGGERATION_INPUT = "tts-exaggeration-input"
    TTS_CFG_WEIGHT_INPUT = "tts-cfg-weight-input"
    TTS_DEVICE_INPUT = "tts-device-input"
    TTS_NANO_INPUT = "tts-nano-input"


class WidgetChatterboxTTSSettingsVertical(Vertical):
    def __init__(
        self,
        chatterbox_params: ChatterboxParamsModel,
        *args,
        **kwargs,
    ) -> None:
        """Only reads chatterbox_params. The changes go up as ValueChanged
        and WidgetTTSContainer writes them."""
        super().__init__(*args, **kwargs)
        self.chatterbox_params = chatterbox_params

    def compose(self) -> ComposeResult:
        yield WidgetVoiceProfilesVertical(self.chatterbox_params)

        yield WidgetSectionHeader("CHATTERBOX PARAMS")

        yield WidgetLabeledSliderRow(
            "Exaggeration:",
            0,
            2,
            self.chatterbox_params.exaggeration,
            step=0.1,
            id=ChatterboxTTSInputWidgetIds.TTS_EXAGGERATION_INPUT,
        )
        yield WidgetLabeledSliderRow(
            "Pace (cfg):",
            0,
            1,
            self.chatterbox_params.cfg_weight,
            step=0.05,
            id=ChatterboxTTSInputWidgetIds.TTS_CFG_WEIGHT_INPUT,
        )
        yield WidgetLabeledSelectRow(
            "Device: ",
            CHATTERBOX_DEVICE_OPTIONS,
            self.chatterbox_params.device,
            id=ChatterboxTTSInputWidgetIds.TTS_DEVICE_INPUT,
        )
        yield WidgetLabeledSwitchRow(
            "Nano model:",
            self.chatterbox_params.nano,
            id=ChatterboxTTSInputWidgetIds.TTS_NANO_INPUT,
        )
