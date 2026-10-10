from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol
from edceleste.services.models.settings_model import TtsProviderParams


class RenameVoiceProfileUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    def __call__(
        self, old_profile_name: str, new_profile_name: str, params: TtsProviderParams
    ) -> None:
        """Renames the profile file and its sample on disk, nothing is cloned
        again. params are the TTS settings as they are on the screen now.
        Raises FileExistsError when the new name is taken. The settings are not
        touched, even when this is the active profile."""
        self.voice_cloning_protocol.rename_profile(
            old_profile_name, new_profile_name, params
        )
