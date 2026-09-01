from typing import Protocol
from typing import AsyncGenerator
from edceleste.services.tts_providers.chatterbox_tts_provider import VoiceCloningState


class VoiceCloningProtocol(Protocol):
    async def clone_voice(
        self, path_to_audio_file: str, profile_name: str
    ) -> "AsyncGenerator[VoiceCloningState, None]": ...

    def get_available_profiles(self) -> list[str]: ...

    def remove_profile(self, profile_name: str) -> None: ...

    async def play_sample_voice(self, profile_name: str) -> None: ...
