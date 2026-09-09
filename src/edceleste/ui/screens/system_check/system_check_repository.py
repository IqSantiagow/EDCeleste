from edceleste.use_cases.system_check.system_check_use_case import SystemCheckUseCase
from edceleste.services.models.cold_start_status import ColdStartStatus
from collections.abc import AsyncGenerator


class SystemCheckRepository:
    def __init__(self, system_check_use_case: SystemCheckUseCase):
        self.system_check_use_case = system_check_use_case

    async def run_system_check(
        self,
    ) -> AsyncGenerator[tuple[str, ColdStartStatus], None]:
        async for service_name, status in self.system_check_use_case():
            yield service_name, status

    def get_service_names(self) -> list[str]:
        return self.system_check_use_case.service_names
