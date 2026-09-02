from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    VoiceAnalysisResult,
)


class AnalyzeVoiceSampleUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    def __call__(self, path_to_audio_file: str) -> VoiceAnalysisResult:
        return self.voice_cloning_protocol.perform_sample_voice_analysis_and_validate(
            path_to_audio_file
        )
