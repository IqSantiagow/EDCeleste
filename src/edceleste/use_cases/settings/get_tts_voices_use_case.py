from edceleste.protocols.tts_protocol import TTSProtocol


class GetTTSVoicesUseCase:
    def __init__(self, tts_protocol: TTSProtocol):
        self.tts_protocol = tts_protocol

    async def __call__(self) -> list[str]:
        """Goes to the network for the edge-tts voice list and returns the
        voice short names, e.g. "en-US-AriaNeural". Raises when the network
        call fails."""
        return await self.tts_protocol.fetch_edge_tts_voice_names()
