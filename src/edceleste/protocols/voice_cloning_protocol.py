from typing import Protocol
from typing import AsyncGenerator
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    VoiceAnalysisResult,
    VoiceCloningState,
)


class VoiceCloningProtocol(Protocol):
    async def clone_voice(
        self, path_to_audio_file: str, profile_name: str
    ) -> "AsyncGenerator[VoiceCloningState, None]": ...

    def get_available_profiles(self) -> list[str]: ...

    def remove_profile(self, profile_name: str) -> None: ...

    def rename_profile(self, old_profile_name: str, new_profile_name: str) -> None: ...

    async def preview_voice_sample(self, profile_name: str, text: str) -> None: ...

    async def play_sample_voice(self, profile_name: str) -> None: ...

    async def play_audio_file(self, path_to_audio_file: str) -> None: ...

    def perform_sample_voice_analysis_and_validate(
        self, path_to_audio_file: str
    ) -> VoiceAnalysisResult: ...
