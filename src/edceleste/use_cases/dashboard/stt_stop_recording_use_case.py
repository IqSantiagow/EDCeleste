from edceleste.protocols.stt_protocol import SttProtocol


class SttStopRecordingUseCase:
    def __init__(self, stt_protocol: SttProtocol) -> None:
        self.stt_protocol = stt_protocol

    def __call__(self) -> str | None:
        return self.stt_protocol.stop_recording()
