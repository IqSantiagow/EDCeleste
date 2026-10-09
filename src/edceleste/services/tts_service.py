import logging
from typing import AsyncGenerator, Literal

import edge_tts

from edceleste.services.event_bus import EventBus
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.services.exceptions.voice_cloning_exception import (
    VoiceCloningException,
)
from edceleste.services.settings_service import SettingsService
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
    VoiceAnalysisResult,
    VoiceCloningState,
)
from edceleste.services.tts_providers.tts_provider_protocol import TTSProviderProtocol
from edceleste.services.voice_lab_service import VoiceLabService

logger = logging.getLogger(__name__)

TTS_PROVIDER_CLASSES = {
    "edge": EdgeTTSProvider,
    "chatterbox": ChatterboxTTSProvider,
}


class TTSEvent:
    def __init__(self, text: str):
        """Published on the event bus by LLMService for every finished text
        block of a reply. TTSService says the text out loud."""
        self.text = text


class TTSService:
    provider_type: str | None = None
    provider: TTSProviderProtocol | None = None

    def __init__(
        self,
        event_bus: EventBus,
        settings_service: SettingsService,
        voice_lab_service: VoiceLabService,
    ) -> None:
        """Only stores the dependencies and subscribes to the event bus. The
        provider stays None until reload_service() builds it.

        Subscriptions:
        - TTSEvent -> speak_text_from_tts_event
        """
        self.__event_bus = event_bus
        self.__settings_service = settings_service
        self.__voice_lab_service = voice_lab_service
        self.__event_bus.subscribe(TTSEvent, self.speak_text_from_tts_event)

    def build_provider(self, settings: SettingsModel) -> TTSProviderProtocol:
        """Creates a new provider object for settings.tts.provider.type. Cheap,
        no model is loaded here, Chatterbox loads it on the first use. Raises
        KeyError for a provider type not in TTS_PROVIDER_CLASSES."""
        provider_class = TTS_PROVIDER_CLASSES[settings.tts.provider.type]
        return provider_class(settings, self.__voice_lab_service)

    async def synthesize_and_play(self, text):
        """Turns the text into speech AND plays it on the speakers. Waits until
        the audio has finished, so the next text is not spoken over this one.
        Fails when reload_service() has not built the provider yet. Provider
        errors are raised."""
        logger.info("Synthesizing TTS for text: %s", text)
        await self.provider.synthesize_and_play(text)

    async def speak_text_from_tts_event(self, event: TTSEvent):
        """Runs when a TTSEvent is published on the event bus. Says the text
        out loud and returns when the audio has finished."""
        logger.info("Received TTS request: %s", event.text)
        await self.synthesize_and_play(event.text)

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Builds a throwaway provider for the new settings and lets it check
        its own fields (Edge: voice, Chatterbox: profile). The active provider
        is not touched."""
        return self.build_provider(new_settings).validate_settings(new_settings)

    def reload_service(self):
        """Applies the saved TTS settings. Called by cold_start() and after
        the settings change.
        A different provider type -> builds a new provider, the old one and
        its loaded model are dropped.
        The same type -> the active provider takes the new settings itself, so
        Chatterbox can keep its loaded model when only e.g. the volume changed.
        """
        new_settings = self.__settings_service.get_settings()

        if new_settings.tts.provider.type != self.provider_type:
            self.provider_type = new_settings.tts.provider.type
            self.provider = self.build_provider(new_settings)
        else:
            self.provider.reload_provider(new_settings)

    async def fetch_edge_tts_voice_names(self) -> list[str]:
        """Asks the Microsoft Edge voice service over the network for every
        voice name, e.g. "en-GB-SoniaNeural". Works whichever provider is
        active. Network errors are raised."""
        return [voice["ShortName"] for voice in await edge_tts.list_voices()]

    async def clone_voice(
        self, path_to_audio_file: str, profile_name: str
    ) -> AsyncGenerator[VoiceCloningState, None]:
        """Makes a new Chatterbox voice profile from an audio file and yields
        every finished step, so the UI can show progress. Writes files to the
        voices folder. Raises VoiceCloningException when the active provider
        is not Chatterbox. See ChatterboxTTSProvider.clone_voice for the steps.
        """
        if not isinstance(self.provider, ChatterboxTTSProvider):
            raise VoiceCloningException(
                "The active TTS provider does not support voice cloning. "
                "Switch the TTS provider to 'chatterbox' and try again."
            )

        logger.info(
            "Cloning voice profile '%s' from audio file: %s",
            profile_name,
            path_to_audio_file,
        )
        async for cloning_state in self.provider.clone_voice(
            path_to_audio_file, profile_name
        ):
            yield cloning_state

    def get_available_profiles(self) -> list[str]:
        """Voice profile names from the voices folder, without ".pt". Empty
        when the active provider is not Chatterbox, even if profiles exist on
        disk."""
        if not isinstance(self.provider, ChatterboxTTSProvider):
            return []

        return self.provider.get_available_profiles()

    def remove_profile(self, profile_name: str) -> None:
        """Deletes the profile file and its sample from disk. Raises
        VoiceCloningException when the active provider is not Chatterbox."""
        if not isinstance(self.provider, ChatterboxTTSProvider):
            raise VoiceCloningException(
                "The active TTS provider does not support voice profiles. "
                "Switch the TTS provider to 'chatterbox' and try again."
            )

        self.provider.remove_profile(profile_name)

    def rename_profile(self, old_profile_name: str, new_profile_name: str) -> None:
        """Renames the profile file and its sample on disk. Raises
        VoiceCloningException when the active provider is not Chatterbox and
        FileExistsError when the new name is taken."""
        if not isinstance(self.provider, ChatterboxTTSProvider):
            raise VoiceCloningException(
                "The active TTS provider does not support voice profiles. "
                "Switch the TTS provider to 'chatterbox' and try again."
            )

        self.provider.rename_profile(old_profile_name, new_profile_name)

    async def preview_voice_sample(self, profile_name: str, text: str) -> None:
        """Speaks the text with the given profile and waits until it has
        played. Nothing is saved. Raises VoiceCloningException when the active
        provider is not Chatterbox."""
        if not isinstance(self.provider, ChatterboxTTSProvider):
            raise VoiceCloningException(
                "The active TTS provider does not support voice profiles. "
                "Switch the TTS provider to 'chatterbox' and try again."
            )

        await self.provider.preview_voice_sample(profile_name, text)

    async def play_sample_voice(self, profile_name: str) -> None:
        """Plays the sample saved when the profile was cloned and waits until
        it has played. No speech is generated. Raises VoiceCloningException
        when the active provider is not Chatterbox."""
        if not isinstance(self.provider, ChatterboxTTSProvider):
            raise VoiceCloningException(
                "The active TTS provider does not support voice profiles. "
                "Switch the TTS provider to 'chatterbox' and try again."
            )

        await self.provider.play_sample_voice(profile_name)

    async def play_audio_file(self, path_to_audio_file: str) -> None:
        """Plays any audio file at the TTS volume, without voice effects, and
        waits until it has played. Used to listen to a clip before cloning.
        Raises VoiceCloningException when the active provider is not
        Chatterbox."""
        if not isinstance(self.provider, ChatterboxTTSProvider):
            raise VoiceCloningException(
                "The active TTS provider does not support voice profiles. "
                "Switch the TTS provider to 'chatterbox' and try again."
            )

        await self.provider.play_audio_file(path_to_audio_file)

    def perform_sample_voice_analysis_and_validate(
        self, path_to_audio_file: str
    ) -> VoiceAnalysisResult:
        """Reads the audio file and measures it for the clone screen: length,
        loudness, clipping, noise and a waveform. A too short clip is not an
        error, it comes back with is_valid False. Raises VoiceCloningException
        when the active provider is not Chatterbox."""
        if not isinstance(self.provider, ChatterboxTTSProvider):
            raise VoiceCloningException(
                "The active TTS provider does not support voice profiles. "
                "Switch the TTS provider to 'chatterbox' and try again."
            )

        return self.provider.perform_sample_voice_analysis_and_validate(
            path_to_audio_file
        )

    def get_available_device(self) -> Literal["cuda", "cpu"]:
        """Device "auto" would pick for Chatterbox. Always "cpu" when the
        active provider is not Chatterbox, even on a machine with a GPU."""
        if not isinstance(self.provider, ChatterboxTTSProvider):
            return "cpu"

        return self.provider.get_available_device()

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Builds the provider (reload_service). No model is loaded and nothing
           is spoken, so a broken voice shows up only on the first reply.
        3. Yields completed. Never raises, an error ends up in the status
           message.
        """
        status = ColdStartStatus(
            service="tts",
            message=None,
            is_critical=False,
            completed=False,
        )
        yield status
        try:
            self.reload_service()
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status
