from edceleste.protocols.instinct_protocol import InstinctProtocol
from edceleste.services.models.instinct_status import InstinctStatus


class GetInstinctStatusUseCase:
    def __init__(self, instinct_protocol: InstinctProtocol):
        self.instinct_protocol = instinct_protocol

    def __call__(self) -> InstinctStatus:
        """Cheap, safe to poll from the UI: model state, download progress,
        running device and the last failure. No network."""
        return self.instinct_protocol.get_status()
