from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol


class RenameVoiceProfileUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    def __call__(self, old_profile_name: str, new_profile_name: str) -> None:
        self.voice_cloning_protocol.rename_profile(old_profile_name, new_profile_name)
