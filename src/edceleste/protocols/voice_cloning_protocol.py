from typing import Protocol


class VoiceCloningProtocol(Protocol):
    async def clone_voice(self, path_to_audio_file: str, profile_name: str) -> None: ...

    def get_available_profiles(self) -> list[str]: ...
