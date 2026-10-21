from collections.abc import AsyncGenerator

from edceleste.protocols.stt_protocol import SttProtocol


class StreamSttTranscriptionsUseCase:
    def __init__(self, stt_protocol: SttProtocol) -> None:
        self.stt_protocol = stt_protocol

    def __call__(self) -> AsyncGenerator[str, None]:
        """Never ends. Gives every spoken text, from the mic button or from the
        hotkey, once Whisper has turned it into text.

        Only one caller may run it, the STT queue does not copy items for a
        second listener."""
        return self.stt_protocol.consume_stt_queue()
