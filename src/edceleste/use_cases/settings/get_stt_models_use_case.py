from edceleste.protocols.stt_protocol import SttProtocol


class GetSttModelsUseCase:
    def __init__(self, stt_protocol: SttProtocol):
        self.stt_protocol = stt_protocol

    def __call__(self) -> list[str]:
        return self.stt_protocol.get_stt_models()
