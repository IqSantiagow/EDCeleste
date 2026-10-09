from edceleste.protocols.instinct_protocol import InstinctProtocol


class DownloadInstinctModelUseCase:
    def __init__(self, instinct_protocol: InstinctProtocol):
        self.instinct_protocol = instinct_protocol

    def __call__(self) -> None:
        """Starts the Instinct download in an asyncio task and returns at once,
        so it must run on the app event loop. Does nothing when a download or
        load is already running. Progress and errors are read later with
        GetInstinctStatusUseCase, nothing is raised here."""
        self.instinct_protocol.download_and_load_model_in_background()
