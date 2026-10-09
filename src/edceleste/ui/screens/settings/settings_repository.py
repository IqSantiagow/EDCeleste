from typing import AsyncGenerator, Literal

from edceleste.services.models.instinct_status import InstinctStatus
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    VoiceAnalysisResult,
    VoiceCloningState,
)
from edceleste.services.models.keybinds_model import Keybind
from edceleste.services.models.settings_model import (
    LLMProviderModel,
    SettingsIssueModel,
    SettingsModel,
)
from edceleste.use_cases.settings.exceptions.settings_validation_exception import (
    SettingsValidationException,
)
from edceleste.use_cases.settings.analyze_voice_sample_use_case import (
    AnalyzeVoiceSampleUseCase,
)
from edceleste.use_cases.settings.clone_voice_use_case import CloneVoiceUseCase
from edceleste.use_cases.settings.get_available_device_use_case import (
    GetAvailableDeviceUseCase,
)
from edceleste.use_cases.settings.get_available_voice_profiles_use_case import (
    GetAvailableVoiceProfilesUseCase,
)
from edceleste.use_cases.settings.fetch_llm_model_names_use_case import (
    FetchLlmModelNamesUseCase,
)
from edceleste.use_cases.settings.get_settings_use_case import GetSettingsUseCase
from edceleste.use_cases.settings.get_stt_models_use_case import GetSttModelsUseCase
from edceleste.use_cases.settings.get_stt_input_devices_use_case import (
    GetSttInputDevicesUseCase,
)
from edceleste.use_cases.settings.get_tts_voices_use_case import GetTTSVoicesUseCase
from edceleste.use_cases.settings.play_audio_file_use_case import PlayAudioFileUseCase
from edceleste.use_cases.settings.play_sample_voice_use_case import (
    PlaySampleVoiceUseCase,
)
from edceleste.use_cases.settings.preview_voice_sample_use_case import (
    PreviewVoiceSampleUseCase,
)
from edceleste.use_cases.settings.remove_voice_profile_use_case import (
    RemoveVoiceProfileUseCase,
)
from edceleste.use_cases.settings.rename_voice_profile_use_case import (
    RenameVoiceProfileUseCase,
)
from edceleste.use_cases.settings.settings_get_keybinds_use_case import (
    SettingsGetKeybindsUseCase,
)
from edceleste.use_cases.settings.settings_load_keybinds_use_case import (
    SettingsLoadKeybindsUseCase,
)
from edceleste.use_cases.settings.find_llm_connection_error_use_case import (
    FindLlmConnectionErrorUseCase,
)
from edceleste.use_cases.settings.cancel_instinct_download_use_case import (
    CancelInstinctDownloadUseCase,
)
from edceleste.use_cases.settings.download_instinct_model_use_case import (
    DownloadInstinctModelUseCase,
)
from edceleste.use_cases.settings.get_instinct_download_size_use_case import (
    GetInstinctDownloadSizeUseCase,
)
from edceleste.use_cases.settings.get_instinct_status_use_case import (
    GetInstinctStatusUseCase,
)
from edceleste.use_cases.settings.update_settings_use_case import UpdateSettingsUseCase


class SettingsRepository:
    """The settings screen and its widgets talk to the services only through
    this class. Every method passes the call to one use case."""

    def __init__(
        self,
        settings_load_keybinds_use_case: SettingsLoadKeybindsUseCase,
        settings_get_keybinds_use_case: SettingsGetKeybindsUseCase,
        update_settings_use_case: UpdateSettingsUseCase,
        get_settings_use_case: GetSettingsUseCase,
        get_tts_voices_use_case: GetTTSVoicesUseCase,
        fetch_llm_model_names_use_case: FetchLlmModelNamesUseCase,
        find_llm_connection_error_use_case: FindLlmConnectionErrorUseCase,
        get_instinct_status_use_case: GetInstinctStatusUseCase,
        get_instinct_download_size_use_case: GetInstinctDownloadSizeUseCase,
        download_instinct_model_use_case: DownloadInstinctModelUseCase,
        cancel_instinct_download_use_case: CancelInstinctDownloadUseCase,
        get_stt_models_use_case: GetSttModelsUseCase,
        get_stt_input_devices_use_case: GetSttInputDevicesUseCase,
        clone_voice_use_case: CloneVoiceUseCase,
        get_available_voice_profiles_use_case: GetAvailableVoiceProfilesUseCase,
        remove_voice_profile_use_case: RemoveVoiceProfileUseCase,
        rename_voice_profile_use_case: RenameVoiceProfileUseCase,
        play_sample_voice_use_case: PlaySampleVoiceUseCase,
        play_audio_file_use_case: PlayAudioFileUseCase,
        analyze_voice_sample_use_case: AnalyzeVoiceSampleUseCase,
        preview_voice_sample_use_case: PreviewVoiceSampleUseCase,
        get_available_device_use_case: GetAvailableDeviceUseCase,
    ) -> None:
        """Only stores the use cases. Nothing is read or loaded here."""
        self.settings_load_keybinds_use_case = settings_load_keybinds_use_case
        self.settings_get_keybinds_use_case = settings_get_keybinds_use_case
        self.update_settings_use_case = update_settings_use_case
        self.get_settings_use_case = get_settings_use_case
        self.get_tts_voices_use_case = get_tts_voices_use_case
        self.fetch_llm_model_names_use_case = fetch_llm_model_names_use_case
        self.find_llm_connection_error_use_case = find_llm_connection_error_use_case
        self.get_instinct_status_use_case = get_instinct_status_use_case
        self.get_instinct_download_size_use_case = get_instinct_download_size_use_case
        self.download_instinct_model_use_case = download_instinct_model_use_case
        self.cancel_instinct_download_use_case = cancel_instinct_download_use_case
        self.get_stt_models_use_case = get_stt_models_use_case
        self.get_stt_input_devices_use_case = get_stt_input_devices_use_case
        self.clone_voice_use_case = clone_voice_use_case
        self.get_available_voice_profiles_use_case = (
            get_available_voice_profiles_use_case
        )
        self.remove_voice_profile_use_case = remove_voice_profile_use_case
        self.rename_voice_profile_use_case = rename_voice_profile_use_case
        self.play_sample_voice_use_case = play_sample_voice_use_case
        self.play_audio_file_use_case = play_audio_file_use_case
        self.analyze_voice_sample_use_case = analyze_voice_sample_use_case
        self.preview_voice_sample_use_case = preview_voice_sample_use_case
        self.get_available_device_use_case = get_available_device_use_case

    def get_keybinds(self) -> list[Keybind]:
        """Returns the keybinds already parsed by load_keybinds(). Does not read
        the .binds file again."""
        return self.settings_get_keybinds_use_case()

    def load_keybinds(self) -> None:
        """Parses the game's .binds file again and refreshes the keybinds cache.
        Called by the dashboard screen on mount."""
        self.settings_load_keybinds_use_case()

    async def validate_and_save_settings(
        self, new_settings: SettingsModel
    ) -> list[SettingsIssueModel]:
        """1. Every service checks new_settings, the LLM check goes to the
           network.
        2. Any issue: nothing is saved and all issues are returned.
        3. No issue: the settings are written to config.yaml, every service
           reloads with them and an empty list is returned.
        Other errors are not caught.
        """
        try:
            await self.update_settings_use_case(new_settings)
            return []
        except SettingsValidationException as e:
            return e.issues

    def get_settings(self) -> SettingsModel:
        """The settings as last loaded or saved by SettingsService. Does not read
        config.yaml again."""
        return self.get_settings_use_case()

    async def fetch_edge_tts_voice_names(self) -> list[str]:
        """Asks Microsoft over the network for every edge-tts voice and returns
        their short names, e.g. "en-US-AriaNeural"."""
        return await self.get_tts_voices_use_case()

    async def fetch_available_model_names(
        self, provider: LLMProviderModel | None = None
    ) -> list[str]:
        """Asks the provider for its model list over the network. None uses the
        saved provider. An empty list means "we do not know", not "no models"."""
        return await self.fetch_llm_model_names_use_case(provider)

    async def find_llm_connection_error(self, provider: LLMProviderModel) -> str | None:
        """Sends one real test prompt to the LLM with the given, maybe unsaved,
        provider settings. Costs a few tokens. Returns None when the LLM
        answered, else a short error text for the screen with the API key
        redacted."""
        return await self.find_llm_connection_error_use_case(provider)

    def get_instinct_status(self) -> InstinctStatus:
        """Snapshot of the local Instinct model: state, download progress, the
        device it runs on and the last failure."""
        return self.get_instinct_status_use_case()

    async def fetch_instinct_download_size(self) -> int | None:
        """Size of the Instinct model in bytes, asked from the Hugging Face Hub in
        a thread. Cached after the first answer. None when the Hub cannot be
        reached."""
        return await self.get_instinct_download_size_use_case()

    def download_instinct_model(self) -> None:
        """Does not wait. Starts downloading (if needed) and loading Instinct
        as a background task. Does nothing when a download or load already
        runs. Follow the progress with get_instinct_status()."""
        self.download_instinct_model_use_case()

    def cancel_instinct_download(self) -> None:
        """Only raises a cancel flag. The running download stops at its next
        check, not at once."""
        self.cancel_instinct_download_use_case()

    async def clone_voice(
        self, path_to_audio_file: str, profile_name: str
    ) -> AsyncGenerator[VoiceCloningState, None]:
        """Builds a new chatterbox voice profile from an audio file and yields
        every cloning step, so the UI can show progress. Loads the chatterbox
        model first if needed, which is slow. Raises when the active TTS
        provider is not chatterbox or the file does not exist."""
        async for cloning_state in self.clone_voice_use_case(
            path_to_audio_file, profile_name
        ):
            yield cloning_state

    def get_available_voice_profiles(self) -> list[str]:
        """Names of the saved chatterbox voice profiles, without the ".pt"
        extension. Empty when the active TTS provider is not chatterbox."""
        return self.get_available_voice_profiles_use_case()

    def remove_voice_profile(self, profile_name: str) -> None:
        """Deletes the profile file and its sample .wav from disk. Raises when the
        active TTS provider is not chatterbox."""
        self.remove_voice_profile_use_case(profile_name)

    def rename_voice_profile(
        self, old_profile_name: str, new_profile_name: str
    ) -> None:
        """Renames the profile file and its sample .wav on disk. Raises when the
        active TTS provider is not chatterbox."""
        self.rename_voice_profile_use_case(old_profile_name, new_profile_name)

    async def preview_voice_sample(self, profile_name: str, text: str) -> None:
        """Generates speech for text with the profile's voice, applies the Voice
        Lab effects and plays it out loud. Returns when playback ends."""
        await self.preview_voice_sample_use_case(profile_name, text)

    async def play_sample_voice(self, profile_name: str) -> None:
        """Plays out loud the sample .wav saved with the profile when it was
        cloned. Returns when playback ends. Raises FileNotFoundError when the
        sample is missing."""
        await self.play_sample_voice_use_case(profile_name)

    async def play_audio_file(self, path_to_audio_file: str) -> None:
        """Plays any audio file out loud at the TTS volume, e.g. a recording
        before it is cloned. Returns when playback ends."""
        await self.play_audio_file_use_case(path_to_audio_file)

    def analyze_voice_sample(self, path_to_audio_file: str) -> VoiceAnalysisResult:
        """Checks if the audio file is good for cloning (length and similar) and
        returns the measurements with a validation error message, if any."""
        return self.analyze_voice_sample_use_case(path_to_audio_file)

    def get_available_device(self) -> Literal["cuda", "cpu"]:
        """The device chatterbox would run on: "cuda" when a GPU is usable, else
        "cpu". Always "cpu" when the active TTS provider is not chatterbox."""
        return self.get_available_device_use_case()

    def get_stt_models(self) -> list[str]:
        """Names of every Whisper model size, e.g. "base" or "small". Nothing is
        downloaded."""
        return self.get_stt_models_use_case()

    def get_stt_input_devices(self) -> list[tuple[str, int]]:
        """Every microphone as (name, sounddevice index). Devices without input
        channels are skipped, and a name seen twice keeps only its first index."""
        return self.get_stt_input_devices_use_case()
