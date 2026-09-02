from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.reactive import reactive

from edceleste.services.models.settings_model import (
    DEFAULT_EDGE_VOICE,
    ChatterboxTTSProviderModel,
    EdgeTTSProviderModel,
    TTSModel,
)
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.widgets.const_ids import (
    SettingsInputWidgetIds,
    SettingsSection,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    ValueChanged,
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_slider_row import (
    WidgetLabeledSliderRow,
)
from edceleste.ui.screens.settings.widgets.tts.widget_chatterbox_tts_settings_vertical import (  # noqa: E501
    WidgetChatterboxTTSSettingsVertical,
)
from edceleste.ui.screens.settings.widgets.tts.widget_edge_tts_settings_vertical import (  # noqa: E501
    WidgetEdgeTTSSettingsVertical,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

ENGINE_OPTIONS = ["Edge TTS", "Chatterbox"]
ENGINE_VALUES = ["edge", "chatterbox"]


def build_default_provider_for_engine(
    engine: str,
) -> EdgeTTSProviderModel | ChatterboxTTSProviderModel:
    if engine == "edge":
        return EdgeTTSProviderModel(type="edge", voice=DEFAULT_EDGE_VOICE)
    return ChatterboxTTSProviderModel(type="chatterbox", profile="")


class WidgetTTSContainer(Vertical):
    provider: reactive[EdgeTTSProviderModel | ChatterboxTTSProviderModel | None] = (
        reactive(None, recompose=True)
    )

    def __init__(
        self,
        tts_model: TTSModel,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.tts_model = tts_model
        self.provider = tts_model.provider

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield WidgetSectionHeader("TTS SETTINGS")
            provider = self.provider
            assert provider is not None, "provider must be set before compose() runs"
            yield WidgetLabeledSelectRow(
                "Engine: ",
                ENGINE_OPTIONS,
                provider.type,
                values=ENGINE_VALUES,
                id=SettingsInputWidgetIds.TTS_PROVIDER_TYPE_INPUT.value,
            )
            if isinstance(provider, EdgeTTSProviderModel):
                yield from self.mount_edge_tts_settings(provider)
            elif isinstance(provider, ChatterboxTTSProviderModel):
                yield from self.mount_chatterbox_settings(provider)
            yield WidgetLabeledSliderRow(
                "Volume:",
                0,
                1,
                self.tts_model.volume,
                step=0.05,
                id=SettingsInputWidgetIds.VOLUME_INPUT.value,
            )

    def on_value_changed(self, message: ValueChanged) -> None:
        provider = self.provider
        assert provider is not None, "provider must be set before on_value_changed runs"
        if message.sender_id == SettingsInputWidgetIds.TTS_PROVIDER_TYPE_INPUT.value:
            if message.new_value != provider.type:
                new_provider = build_default_provider_for_engine(message.new_value)
                self.tts_model.provider = new_provider
                self.provider = new_provider
        elif message.sender_id == SettingsInputWidgetIds.VOICE_INPUT.value:
            if isinstance(provider, EdgeTTSProviderModel):
                provider.voice = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.VOLUME_INPUT.value:
            try:
                self.tts_model.volume = float(message.new_value)
            except ValueError:
                self.log(f"Invalid volume value: {message.new_value}")
                self.notify("Volume must be a number between 0.0 and 1.0.")
                return
        elif message.sender_id == SettingsInputWidgetIds.TTS_PROFILE_INPUT.value:
            if isinstance(provider, ChatterboxTTSProviderModel):
                provider.profile = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.TTS_EXAGGERATION_INPUT.value:
            if isinstance(provider, ChatterboxTTSProviderModel):
                try:
                    provider.exaggeration = float(message.new_value)
                except ValueError:
                    self.log(f"Invalid exaggeration value: {message.new_value}")
                    self.notify("Exaggeration must be a number between 0.0 and 2.0.")
                    return
        elif message.sender_id == SettingsInputWidgetIds.TTS_CFG_WEIGHT_INPUT.value:
            if isinstance(provider, ChatterboxTTSProviderModel):
                try:
                    provider.cfg_weight = float(message.new_value)
                except ValueError:
                    self.log(f"Invalid pace value: {message.new_value}")
                    self.notify("Pace must be a number between 0.0 and 1.0.")
                    return
        elif message.sender_id == SettingsInputWidgetIds.TTS_DEVICE_INPUT.value:
            if isinstance(provider, ChatterboxTTSProviderModel):
                provider.device = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.TTS_NANO_INPUT.value:
            if isinstance(provider, ChatterboxTTSProviderModel):
                provider.nano = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.TTS,
                new_value=self.tts_model,
            )
        )

    def mount_chatterbox_settings(
        self, chatterbox_provider: ChatterboxTTSProviderModel
    ) -> ComposeResult:
        yield WidgetChatterboxTTSSettingsVertical(chatterbox_provider)

    def mount_edge_tts_settings(
        self, edge_provider: EdgeTTSProviderModel
    ) -> ComposeResult:
        yield WidgetEdgeTTSSettingsVertical(edge_provider)
