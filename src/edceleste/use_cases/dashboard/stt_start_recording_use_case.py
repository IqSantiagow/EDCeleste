from edceleste.protocols.stt_protocol import SttProtocol


class SttStartRecordingUseCase:
    def __init__(self, stt_protocol: SttProtocol) -> None:
        self.stt_protocol = stt_protocol

    def __call__(self) -> None:
        self.stt_protocol.start_recording()
