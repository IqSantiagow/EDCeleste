from dependency_injector.wiring import Provide, inject
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import LoadingIndicator

from edceleste.containers.main_container import Container
from edceleste.services.models.settings_model import EdgeTTSProviderModel
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.const_ids import SettingsInputWidgetIds
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    WidgetLabeledSelectRow,
)


class WidgetEdgeTTSSettingsVertical(Vertical):
    voices: reactive[list[str] | None] = reactive(None, recompose=True)

    @inject
    def __init__(
        self,
        edge_tts_provider_model: EdgeTTSProviderModel,
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.edge_tts_provider_model = edge_tts_provider_model
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        self.call_later(self.fetch_voices)

    def compose(self) -> ComposeResult:
        if self.voices is None:
            yield LoadingIndicator(id="loading-voices-indicator")
        else:
            yield WidgetLabeledSelectRow(
                "Voice: ",
                options=self.voices,
                value=self.edge_tts_provider_model.voice,
                id=SettingsInputWidgetIds.VOICE_INPUT.value,
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
