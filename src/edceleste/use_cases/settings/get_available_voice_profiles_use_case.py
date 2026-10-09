from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol


class GetAvailableVoiceProfilesUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    def __call__(self) -> list[str]:
        """Reads the voices folder on disk every time. Names come without
        ".pt". Empty when the folder does not exist yet or the TTS provider is
        not chatterbox."""
        return self.voice_cloning_protocol.get_available_profiles()
