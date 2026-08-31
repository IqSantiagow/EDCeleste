from textual.app import ComposeResult
from textual.containers import Vertical
from textual.validation import Number

from edceleste.services.models.settings_model import EdgeTTSProviderModel, TTSModel
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.widgets.const_ids import (
    SettingsInputWidgetIds,
    SettingsSection,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_dynamic_input_row import (  # noqa: E501
    WidgetLabeledDynamicInputRow,
)
from edceleste.ui.screens.settings.widgets.tts.widget_edge_tts_settings_vertical import (  # noqa: E501
    WidgetEdgeTTSSettingsVertical,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


class WidgetTTSContainer(Vertical):
    def __init__(
        self,
        tts_model: TTSModel,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.tts_model = tts_model

    def compose(self) -> ComposeResult:
        with Vertical():
            yield WidgetSectionHeader("TTS SETTINGS")
            provider = self.tts_model.provider
            if isinstance(provider, EdgeTTSProviderModel):
                yield from self.mount_edge_tts_settings(provider)
            yield WidgetLabeledDynamicInputRow(
                "Volume:",
                f"{self.tts_model.volume}",
                lambda value: self.log(f"Volume submitted: {value}"),
                type="number",
                validators=[Number(minimum=0, maximum=1)],
                id=SettingsInputWidgetIds.VOLUME_INPUT.value,
            )

    def on_value_changed(self, message: ValueChanged) -> None:
        if message.sender_id == SettingsInputWidgetIds.VOICE_INPUT.value:
            if isinstance(self.tts_model.provider, EdgeTTSProviderModel):
                self.tts_model.provider.voice = message.new_value
        elif message.sender_id == SettingsInputWidgetIds.VOLUME_INPUT.value:
            try:
                self.tts_model.volume = float(message.new_value)
            except ValueError:
                self.log(f"Invalid volume value: {message.new_value}")
                self.notify("Volume must be a number between 0.0 and 1.0.")
                return

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.TTS,
                new_value=self.tts_model,
            )
        )

    def mount_chatterbox_settings(self) -> None: ...

    def mount_edge_tts_settings(
        self, edge_provider: EdgeTTSProviderModel
    ) -> ComposeResult:
        yield WidgetEdgeTTSSettingsVertical(edge_provider)
