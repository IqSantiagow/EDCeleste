from typing import AsyncGenerator, Protocol

from edceleste.services.models.cold_start_status import ColdStartStatus


class BaseServiceProtocol(Protocol):
    def cold_start(self) -> "AsyncGenerator[ColdStartStatus, None]":
        """Perform a cold start of the service, yielding status updates."""
        ...
