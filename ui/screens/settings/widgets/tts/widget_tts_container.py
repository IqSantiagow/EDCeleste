from dependency_injector.wiring import Provide, inject
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.validation import Number
from textual.widgets import LoadingIndicator

from containers.main_container import Container
from services.models.settings_model import TTSModel
from ui.screens.settings.events.settings_events import SectionSettingsChanged
from ui.screens.settings.settings_repository import SettingsRepository
from ui.screens.settings.widgets.const_ids import (
    SettingsInputWidgetIds,
    SettingsSection,
)
from ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    ValueChanged,
    WidgetLabeledSelectRow,
)
from ui.screens.settings.widgets.inputs.widget_labeled_dynamic_input_row import (
    WidgetLabeledDynamicInputRow,
)
from ui.widgets.common.widget_section_header import WidgetSectionHeader


class WidgetTTSContainer(Vertical):
    voices: reactive[list[str] | None] = reactive(None, recompose=True)

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
        super().__init__(*args, **kwargs)
        self.tts_model = tts_model
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        self.call_later(self.fetch_voices)

    def compose(self) -> ComposeResult:
        if self.voices is None:
            yield LoadingIndicator(id="loading-voices-indicator")
        else:
            with Vertical():
                yield WidgetSectionHeader("TTS SETTINGS")
                yield WidgetLabeledSelectRow(
                    "Voice: ",
                    options=self.voices,
                    value=self.tts_model.voice,
                    id=SettingsInputWidgetIds.VOICE_INPUT.value,
                )
                yield WidgetLabeledDynamicInputRow(
                    "Volume:",
                    f"{self.tts_model.volume}",
                    lambda value: self.log(f"Volume submitted: {value}"),
                    type="number",
                    validators=[Number(minimum=0, maximum=1)],
                    id=SettingsInputWidgetIds.VOLUME_INPUT.value,
                )

    @work
    async def fetch_voices(self) -> None:
        try:
            self.voices = await self.settings_repository.get_voices()
        except Exception as e:
            self.log(f"Error fetching voices: {e}")
            self.notify(
                "Error fetching voices. Please check your internet connection "
                "or TTS service."
            )

    def on_value_changed(self, message: ValueChanged) -> None:
        if message.sender_id == SettingsInputWidgetIds.VOICE_INPUT.value:
            self.tts_model.voice = message.new_value
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
