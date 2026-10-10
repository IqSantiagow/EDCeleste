import enum

from dependency_injector.wiring import Provide, inject
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import LoadingIndicator

from edceleste.containers.main_container import Container
from edceleste.services.models.settings_model import EdgeParamsModel
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    WidgetLabeledSelectRow,
)


class EdgeTTSInputWidgetIds(enum.StrEnum):
    VOICE_INPUT = "voice-input"


class WidgetEdgeTTSSettingsVertical(Vertical):
    voices: reactive[list[str] | None] = reactive(None, recompose=True)

    @inject
    def __init__(
        self,
        edge_params: EdgeParamsModel,
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        *args,
        **kwargs,
    ) -> None:
        """Only reads edge_params. The voice change goes up as ValueChanged and
        WidgetTTSContainer writes it."""
        super().__init__(*args, **kwargs)
        self.edge_params = edge_params
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        """Starts loading the Edge voice list. Until it is in, compose() shows
        a loading indicator."""
        self.call_later(self.fetch_voices)

    def compose(self) -> ComposeResult:
        """Runs again when voices is set: a loading indicator before, the voice
        select after."""
        if self.voices is None:
            yield LoadingIndicator(id="loading-voices-indicator")
        else:
            yield WidgetLabeledSelectRow(
                "Voice: ",
                options=self.voices,
                value=self.edge_params.voice,
                id=EdgeTTSInputWidgetIds.VOICE_INPUT,
            )

    @work
    async def fetch_voices(self) -> None:
        """Worker. Downloads the Edge voice names from Microsoft over the
        network. On error it shows a notification and voices stays None, so
        the loading indicator never goes away."""
        try:
            self.voices = await self.settings_repository.fetch_edge_tts_voice_names()
        except Exception as e:
            self.log(f"Error fetching voices: {e}")
            self.notify(
                "Error fetching voices. Please check your internet connection "
                "or TTS service."
            )
