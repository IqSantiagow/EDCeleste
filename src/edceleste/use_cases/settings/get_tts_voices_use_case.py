from edceleste.protocols.tts_protocol import TTSProtocol


class GetTTSVoicesUseCase:
    def __init__(self, tts_protocol: TTSProtocol):
        self.tts_protocol = tts_protocol

    async def __call__(self) -> list[str]:
        return await self.tts_protocol.get_tts_voices()
