from collections.abc import AsyncGenerator
from typing import Protocol

from edceleste.services.models.service_status import ServiceStatus


class ServiceStatusProtocol(Protocol):
    """Every service shown in the app header (LLM, TTS, MIC, JRNL) has this one
    method, with the same name and the same meaning."""

    def stream_status(self) -> AsyncGenerator[ServiceStatus, None]:
        """A broadcast like GameStateProtocol.stream_game_stats: every call
        gets its own queue. Yields the latest status at once, then a new one
        every time the service starts working, fails or is switched off. Never
        ends by itself, it stops listening when the caller stops iterating."""
        ...
