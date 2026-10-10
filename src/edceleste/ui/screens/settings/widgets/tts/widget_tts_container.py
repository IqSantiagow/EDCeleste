import enum

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive

from edceleste.services.models.settings_model import (
    DEFAULT_EDGE_VOICE,
    ChatterboxParamsModel,
    EdgeParamsModel,
    TTSModel,
    TtsProviderParams,
)
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    ValueChanged,
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_slider_row import (
    WidgetLabeledSliderRow,
)
from edceleste.ui.screens.settings.widgets.tts.widget_chatterbox_tts_settings_vertical import (  # noqa: E501
    ChatterboxTTSInputWidgetIds,
    WidgetChatterboxTTSSettingsVertical,
)
from edceleste.ui.screens.settings.widgets.tts.widget_edge_tts_settings_vertical import (  # noqa: E501
    EdgeTTSInputWidgetIds,
    WidgetEdgeTTSSettingsVertical,
)
from edceleste.ui.screens.settings.widgets.tts.widget_voice_lab_settings_vertical import (  # noqa: E501
    VoiceLabInputWidgetIds,
    WidgetVoiceLabSettingsVertical,
)
from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

ENGINE_OPTIONS = ["Edge TTS", "Chatterbox"]
ENGINE_VALUES = ["edge", "chatterbox"]


def build_default_params_for_engine(engine: str) -> TtsProviderParams:
    """Used when the pilot switches to an engine for the first time on this
    screen. "edge" gets the default Edge voice, anything else gets Chatterbox
    with no voice profile picked."""
    if engine == "edge":
        return EdgeParamsModel(type="edge", voice=DEFAULT_EDGE_VOICE)
    return ChatterboxParamsModel(type="chatterbox", profile="")


class TTSInputWidgetIds(enum.StrEnum):
    TTS_PROVIDER_TYPE_INPUT = "tts-provider-type-input"
    VOLUME_INPUT = "volume-input"


class WidgetTTSContainer(WidgetBaseSettingsContainer):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "TEXT TO SPEECH"

    params: reactive[TtsProviderParams | None] = reactive(None, recompose=True)

    def __init__(
        self,
        tts_model: TTSModel,
        *args,
        **kwargs,
    ) -> None:
        """tts_model is part of the screen's working copy of the settings and
        is changed in place. params is set without triggering a recompose,
        because nothing is composed yet. Remembers the params of every engine
        shown on this screen, so switching back shows them again, and the
        saved engine, for is_modified()."""
        super().__init__(*args, **kwargs)
        self.tts_model = tts_model
        self.params_of_every_engine: dict[str, TtsProviderParams] = {
            tts_model.provider: tts_model.params
        }
        self.saved_engine = tts_model.provider
        self.set_reactive(WidgetTTSContainer.params, tts_model.params)

    def compose(self) -> ComposeResult:
        """Runs again when params change (engine switch). The engine
        select, then the settings of that engine (Edge voice list or
        Chatterbox profiles and params), then the volume slider and the Voice
        Lab block, which are the same for both engines."""
        yield from super().compose()
        with VerticalScroll():
            yield WidgetSectionHeader("TTS SETTINGS")
            params = self.params
            assert params is not None, "params must be set before compose() runs"
            yield WidgetLabeledSelectRow(
                "Engine: ",
                ENGINE_OPTIONS,
                params.type,
                values=ENGINE_VALUES,
                id=TTSInputWidgetIds.TTS_PROVIDER_TYPE_INPUT,
            )
            if isinstance(params, EdgeParamsModel):
                yield from self.compose_edge_tts_settings(params)
            elif isinstance(params, ChatterboxParamsModel):
                yield from self.compose_chatterbox_settings(params)
            yield WidgetLabeledSliderRow(
                "Volume:",
                0,
                1,
                self.tts_model.volume,
                step=0.05,
                id=TTSInputWidgetIds.VOLUME_INPUT,
            )
            yield WidgetVoiceLabSettingsVertical(self.tts_model.voice_lab)

    def on_value_changed(self, message: ValueChanged) -> None:
        """Gets ValueChanged from every row in this section, also from the Edge,
        Chatterbox and Voice Lab blocks, because the message bubbles up.

        Writes the new value into tts_model and posts
        SectionSettingsChanged(TTS) to the settings screen. Nothing is saved
        here. Special cases:
        - engine changed -> the params this engine had on this screen (or its
          defaults the first time) and a recompose. The params of the engine
          left behind stay remembered, with the pilot's unsaved edits,

        - an Edge or Chatterbox field while the other engine is active -> not
          written, but the message is still posted,
        - volume, exaggeration or pace that is not a number -> notification
          and no post.
        """
        params = self.params
        assert params is not None, "params must be set before on_value_changed runs"
        match message.sender_id:
            case TTSInputWidgetIds.TTS_PROVIDER_TYPE_INPUT:
                if message.new_value != params.type:
                    if message.new_value not in self.params_of_every_engine:
                        self.params_of_every_engine[message.new_value] = (
                            build_default_params_for_engine(message.new_value)
                        )
                    new_params = self.params_of_every_engine[message.new_value]
                    self.tts_model.provider = message.new_value
                    self.tts_model.params = new_params
                    self.params = new_params
            case EdgeTTSInputWidgetIds.VOICE_INPUT:
                if isinstance(params, EdgeParamsModel):
                    params.voice = message.new_value
            case TTSInputWidgetIds.VOLUME_INPUT:
                try:
                    self.tts_model.volume = float(message.new_value)
                except ValueError:
                    self.log(f"Invalid volume value: {message.new_value}")
                    self.notify("Volume must be a number between 0.0 and 1.0.")
                    return
            case ChatterboxTTSInputWidgetIds.TTS_PROFILE_INPUT:
                if isinstance(params, ChatterboxParamsModel):
                    params.profile = message.new_value
            case ChatterboxTTSInputWidgetIds.TTS_EXAGGERATION_INPUT:
                if isinstance(params, ChatterboxParamsModel):
                    try:
                        params.exaggeration = float(message.new_value)
                    except ValueError:
                        self.log(f"Invalid exaggeration value: {message.new_value}")
                        self.notify(
                            "Exaggeration must be a number between 0.0 and 2.0."
                        )
                        return
            case ChatterboxTTSInputWidgetIds.TTS_CFG_WEIGHT_INPUT:
                if isinstance(params, ChatterboxParamsModel):
                    try:
                        params.cfg_weight = float(message.new_value)
                    except ValueError:
                        self.log(f"Invalid pace value: {message.new_value}")
                        self.notify("Pace must be a number between 0.0 and 1.0.")
                        return
            case ChatterboxTTSInputWidgetIds.TTS_DEVICE_INPUT:
                if isinstance(params, ChatterboxParamsModel):
                    params.device = message.new_value
            case ChatterboxTTSInputWidgetIds.TTS_NANO_INPUT:
                if isinstance(params, ChatterboxParamsModel):
                    params.nano = message.new_value
            case VoiceLabInputWidgetIds.VOICE_LAB_ENABLED_INPUT:
                self.tts_model.voice_lab.enabled = message.new_value
            case VoiceLabInputWidgetIds.VOICE_LAB_CLARITY_INPUT:
                self.tts_model.voice_lab.clarity = message.new_value
            case VoiceLabInputWidgetIds.VOICE_LAB_REVERB_INPUT:
                self.tts_model.voice_lab.reverb = message.new_value
            case VoiceLabInputWidgetIds.VOICE_LAB_STEREO_WIDTH_INPUT:
                self.tts_model.voice_lab.stereo_width = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.TTS,
                new_value=self.tts_model,
            )
        )

    def is_modified(self) -> bool:
        """True when the engine differs from the saved one, or any input row
        differs from its saved value. The engine is compared here, because
        every engine switch builds the rows again with the new engine as their
        saved value, so the rows alone never show the switch."""
        return self.tts_model.provider != self.saved_engine or super().is_modified()

    def hide_error_and_mark_values_as_saved(self) -> None:
        """After a successful save: everything the base container does, and
        the current engine becomes the saved engine."""
        super().hide_error_and_mark_values_as_saved()
        self.saved_engine = self.tts_model.provider

    def compose_chatterbox_settings(
        self, chatterbox_params: ChatterboxParamsModel
    ) -> ComposeResult:
        """Part of compose(). The Chatterbox block changes chatterbox_params
        through this container's on_value_changed()."""
        yield WidgetChatterboxTTSSettingsVertical(chatterbox_params)

    def compose_edge_tts_settings(self, edge_params: EdgeParamsModel) -> ComposeResult:
        """Part of compose(). The Edge block changes edge_params through this
        container's on_value_changed()."""
        yield WidgetEdgeTTSSettingsVertical(edge_params)
