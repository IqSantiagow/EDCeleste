from edceleste.protocols.stt_protocol import SttProtocol


class GetSttEnabledUseCase:
    def __init__(self, stt_protocol: SttProtocol) -> None:
        self.stt_protocol = stt_protocol

    def __call__(self) -> bool:
        return self.stt_protocol.is_stt_enabled()
