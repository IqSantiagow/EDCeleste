from edceleste.protocols.instinct_protocol import InstinctProtocol


class DownloadInstinctModelUseCase:
    def __init__(self, instinct_protocol: InstinctProtocol):
        self.instinct_protocol = instinct_protocol

    def __call__(self) -> None:
        self.instinct_protocol.download_and_load_model_in_background()
