from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol
from edceleste.services.models.settings_model import TtsProviderParams


class GetAvailableVoiceProfilesUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    def __call__(self, params: TtsProviderParams) -> list[str]:
        """Reads the voices folder on disk every time. Names come without
        ".pt". params are the TTS settings as they are on the screen now. Empty
        when the folder does not exist yet or their provider is not
        chatterbox."""
        return self.voice_cloning_protocol.get_available_profiles(params)
