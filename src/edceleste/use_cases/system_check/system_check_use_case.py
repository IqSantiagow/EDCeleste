from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.cold_start_status import ColdStartStatus
from collections.abc import AsyncGenerator


class SystemCheckUseCase:
    def __init__(self, services: dict[str, BaseServiceProtocol]):
        self.services = services

    async def __call__(self) -> AsyncGenerator[tuple[str, ColdStartStatus], None]:
        for service_name, service in self.services.items():
            async for status in service.cold_start():
                yield service_name, status

    @property
    def service_names(self) -> list[str]:
        return list(self.services.keys())
