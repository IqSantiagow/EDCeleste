from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol
from edceleste.services.models.settings_model import TtsProviderParams


class RemoveVoiceProfileUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    def __call__(self, profile_name: str, params: TtsProviderParams) -> None:
        """Deletes the profile file and its sample from disk. A missing file is
        not an error. params are the TTS settings as they are on the screen
        now. The settings are not touched, even when this is the active
        profile."""
        self.voice_cloning_protocol.remove_profile(profile_name, params)
