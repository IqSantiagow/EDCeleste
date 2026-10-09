from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.cold_start_status import ColdStartStatus
from collections.abc import AsyncGenerator


class SystemCheckUseCase:
    def __init__(self, services: dict[str, BaseServiceProtocol]):
        self.services = services

    async def __call__(self) -> AsyncGenerator[tuple[str, ColdStartStatus], None]:
        """Starts the services: runs cold_start() of each one, one after
        another, in the order of the services dict, and tags every status with
        the service name. A service starts only when the one before it is
        done. When the caller stops iterating, e.g. on a critical failure, the
        services after it are never started."""
        for service_name, service in self.services.items():
            async for status in service.cold_start():
                yield service_name, status

    @property
    def service_names(self) -> list[str]:
        """In the same order the check runs them, so the screen can draw all
        rows before the first status comes."""
        return list(self.services.keys())
