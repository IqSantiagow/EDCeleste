from protocols.stt_protocol import SttProtocol


class GetSttModelsUseCase:
    def __init__(self, stt_protocol: SttProtocol):
        self.stt_protocol = stt_protocol

    async def __call__(self) -> list[str]:
        return await self.stt_protocol.get_stt_models()
