from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol


class GetAvailableVoiceProfilesUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    def __call__(self) -> list[str]:
        return self.voice_cloning_protocol.get_available_profiles()
