from edceleste.protocols.instinct_protocol import InstinctProtocol


class CancelInstinctDownloadUseCase:
    def __init__(self, instinct_protocol: InstinctProtocol):
        self.instinct_protocol = instinct_protocol

    def __call__(self) -> None:
        """Only asks the running Instinct download to stop and returns at
        once. The download stops at its next chunk and deletes the half
        downloaded files. Does nothing when no download is running."""
        self.instinct_protocol.cancel_download()
