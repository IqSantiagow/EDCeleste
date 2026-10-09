from edceleste.protocols.stt_protocol import SttProtocol


class GetSttEnabledUseCase:
    def __init__(self, stt_protocol: SttProtocol) -> None:
        self.stt_protocol = stt_protocol

    def __call__(self) -> bool:
        """Answers from the STT service memory (the value from its last
        reload), it does not read the settings file."""
        return self.stt_protocol.is_stt_enabled()
