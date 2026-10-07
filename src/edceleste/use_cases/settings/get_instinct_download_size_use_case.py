import asyncio

from edceleste.protocols.instinct_protocol import InstinctProtocol


class GetInstinctDownloadSizeUseCase:
    def __init__(self, instinct_protocol: InstinctProtocol):
        self.instinct_protocol = instinct_protocol

    async def __call__(self) -> int | None:
        # asks the Hugging Face Hub over the network, so not on the UI thread
        return await asyncio.to_thread(self.instinct_protocol.get_download_size)
