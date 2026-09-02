from typing import AsyncGenerator, Literal

from edceleste.services.tts_providers.chatterbox_tts_provider import (
    VoiceAnalysisResult,
    VoiceCloningState,
)
from edceleste.services.models.keybinds_model import Keybind
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
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
from edceleste.use_cases.settings.update_settings_use_case import UpdateSettingsUseCase


class SettingsRepository:
    def __init__(
        self,
        settings_load_keybinds_use_case: SettingsLoadKeybindsUseCase,
        settings_get_keybinds_use_case: SettingsGetKeybindsUseCase,
        update_settings_use_case: UpdateSettingsUseCase,
        get_settings_use_case: GetSettingsUseCase,
        get_tts_voices_use_case: GetTTSVoicesUseCase,
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
        self.settings_load_keybinds_use_case = settings_load_keybinds_use_case
        self.settings_get_keybinds_use_case = settings_get_keybinds_use_case
        self.update_settings_use_case = update_settings_use_case
        self.get_settings_use_case = get_settings_use_case
        self.get_tts_voices_use_case = get_tts_voices_use_case
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
        return self.settings_get_keybinds_use_case()

    def load_keybinds(self) -> None:
        self.settings_load_keybinds_use_case()

    def update_settings(self, new_settings: SettingsModel) -> list[SettingsIssueModel]:
        try:
            self.update_settings_use_case(new_settings)
            return []
        except SettingsValidationException as e:
            return e.issues

    def get_settings(self) -> SettingsModel:
        return self.get_settings_use_case()

    async def get_voices(self) -> list[str]:
        return await self.get_tts_voices_use_case()

    async def clone_voice(
        self, path_to_audio_file: str, profile_name: str
    ) -> AsyncGenerator[VoiceCloningState, None]:
        async for cloning_state in self.clone_voice_use_case(
            path_to_audio_file, profile_name
        ):
            yield cloning_state

    def get_available_voice_profiles(self) -> list[str]:
        return self.get_available_voice_profiles_use_case()

    def remove_voice_profile(self, profile_name: str) -> None:
        self.remove_voice_profile_use_case(profile_name)

    def rename_voice_profile(
        self, old_profile_name: str, new_profile_name: str
    ) -> None:
        self.rename_voice_profile_use_case(old_profile_name, new_profile_name)

    async def preview_voice_sample(self, profile_name: str, text: str) -> None:
        await self.preview_voice_sample_use_case(profile_name, text)

    async def play_sample_voice(self, profile_name: str) -> None:
        await self.play_sample_voice_use_case(profile_name)

    async def play_audio_file(self, path_to_audio_file: str) -> None:
        await self.play_audio_file_use_case(path_to_audio_file)

    def analyze_voice_sample(self, path_to_audio_file: str) -> VoiceAnalysisResult:
        return self.analyze_voice_sample_use_case(path_to_audio_file)

    def get_available_device(self) -> Literal["cuda", "cpu"]:
        return self.get_available_device_use_case()

    def get_stt_models(self) -> list[str]:
        return self.get_stt_models_use_case()

    def get_stt_input_devices(self) -> list[tuple[str, int]]:
        return self.get_stt_input_devices_use_case()
