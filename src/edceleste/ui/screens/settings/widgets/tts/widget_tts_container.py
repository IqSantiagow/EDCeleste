import enum

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive

from edceleste.services.models.settings_model import (
    DEFAULT_EDGE_VOICE,
    ChatterboxTTSProviderModel,
    EdgeTTSProviderModel,
    TTSModel,
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


def build_default_provider_for_engine(
    engine: str,
) -> EdgeTTSProviderModel | ChatterboxTTSProviderModel:
    """Used when the pilot switches the engine. "edge" gets the default Edge
    voice, anything else gets Chatterbox with no voice profile picked. The
    settings of the old engine are dropped."""
    if engine == "edge":
        return EdgeTTSProviderModel(type="edge", voice=DEFAULT_EDGE_VOICE)
    return ChatterboxTTSProviderModel(type="chatterbox", profile="")


class TTSInputWidgetIds(enum.StrEnum):
    TTS_PROVIDER_TYPE_INPUT = "tts-provider-type-input"
    VOLUME_INPUT = "volume-input"


class WidgetTTSContainer(WidgetBaseSettingsContainer):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "TEXT TO SPEECH"

    provider: reactive[EdgeTTSProviderModel | ChatterboxTTSProviderModel | None] = (
        reactive(None, recompose=True)
    )

    def __init__(
        self,
        tts_model: TTSModel,
        *args,
        **kwargs,
    ) -> None:
        """tts_model is part of the screen's working copy of the settings and
        is changed in place. provider is set without triggering a recompose,
        because nothing is composed yet."""
        super().__init__(*args, **kwargs)
        self.tts_model = tts_model
        self.set_reactive(WidgetTTSContainer.provider, tts_model.provider)

    def compose(self) -> ComposeResult:
        """Runs again when provider changes (engine switch). The engine
        select, then the settings of that engine (Edge voice list or
        Chatterbox profiles and params), then the volume slider and the Voice
        Lab block, which are the same for both engines."""
        yield from super().compose()
        with VerticalScroll():
            yield WidgetSectionHeader("TTS SETTINGS")
            provider = self.provider
            assert provider is not None, "provider must be set before compose() runs"
            yield WidgetLabeledSelectRow(
                "Engine: ",
                ENGINE_OPTIONS,
                provider.type,
                values=ENGINE_VALUES,
                id=TTSInputWidgetIds.TTS_PROVIDER_TYPE_INPUT,
            )
            if isinstance(provider, EdgeTTSProviderModel):
                yield from self.compose_edge_tts_settings(provider)
            elif isinstance(provider, ChatterboxTTSProviderModel):
                yield from self.compose_chatterbox_settings(provider)
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
        - engine changed -> a fresh default provider and a recompose,
        - an Edge or Chatterbox field while the other engine is active -> not
          written, but the message is still posted,
        - volume, exaggeration or pace that is not a number -> notification
          and no post.
        """
        provider = self.provider
        assert provider is not None, "provider must be set before on_value_changed runs"
        match message.sender_id:
            case TTSInputWidgetIds.TTS_PROVIDER_TYPE_INPUT:
                if message.new_value != provider.type:
                    new_provider = build_default_provider_for_engine(message.new_value)
                    self.tts_model.provider = new_provider
                    self.provider = new_provider
            case EdgeTTSInputWidgetIds.VOICE_INPUT:
                if isinstance(provider, EdgeTTSProviderModel):
                    provider.voice = message.new_value
            case TTSInputWidgetIds.VOLUME_INPUT:
                try:
                    self.tts_model.volume = float(message.new_value)
                except ValueError:
                    self.log(f"Invalid volume value: {message.new_value}")
                    self.notify("Volume must be a number between 0.0 and 1.0.")
                    return
            case ChatterboxTTSInputWidgetIds.TTS_PROFILE_INPUT:
                if isinstance(provider, ChatterboxTTSProviderModel):
                    provider.profile = message.new_value
            case ChatterboxTTSInputWidgetIds.TTS_EXAGGERATION_INPUT:
                if isinstance(provider, ChatterboxTTSProviderModel):
                    try:
                        provider.exaggeration = float(message.new_value)
                    except ValueError:
                        self.log(f"Invalid exaggeration value: {message.new_value}")
                        self.notify(
                            "Exaggeration must be a number between 0.0 and 2.0."
                        )
                        return
            case ChatterboxTTSInputWidgetIds.TTS_CFG_WEIGHT_INPUT:
                if isinstance(provider, ChatterboxTTSProviderModel):
                    try:
                        provider.cfg_weight = float(message.new_value)
                    except ValueError:
                        self.log(f"Invalid pace value: {message.new_value}")
                        self.notify("Pace must be a number between 0.0 and 1.0.")
                        return
            case ChatterboxTTSInputWidgetIds.TTS_DEVICE_INPUT:
                if isinstance(provider, ChatterboxTTSProviderModel):
                    provider.device = message.new_value
            case ChatterboxTTSInputWidgetIds.TTS_NANO_INPUT:
                if isinstance(provider, ChatterboxTTSProviderModel):
                    provider.nano = message.new_value
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

    def compose_chatterbox_settings(
        self, chatterbox_provider: ChatterboxTTSProviderModel
    ) -> ComposeResult:
        """Part of compose(). The Chatterbox block changes chatterbox_provider
        through this container's on_value_changed()."""
        yield WidgetChatterboxTTSSettingsVertical(chatterbox_provider)

    def compose_edge_tts_settings(
        self, edge_provider: EdgeTTSProviderModel
    ) -> ComposeResult:
        """Part of compose(). The Edge block changes edge_provider through this
        container's on_value_changed()."""
        yield WidgetEdgeTTSSettingsVertical(edge_provider)
