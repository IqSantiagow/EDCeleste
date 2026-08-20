from protocols.stt_protocol import SttProtocol


class SttTranscribeAudioUseCase:
    def __init__(self, stt_protocol: SttProtocol) -> None:
        self.stt_protocol = stt_protocol

    def __call__(self, audio_path: str) -> str | None:
        return self.stt_protocol.handle_stt_request(audio_path)
