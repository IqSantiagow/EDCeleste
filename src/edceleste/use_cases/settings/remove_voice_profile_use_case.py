from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol


class RemoveVoiceProfileUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    def __call__(self, profile_name: str) -> None:
        self.voice_cloning_protocol.remove_profile(profile_name)
