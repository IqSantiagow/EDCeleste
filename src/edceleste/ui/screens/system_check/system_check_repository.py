from edceleste.use_cases.system_check.system_check_use_case import SystemCheckUseCase
from edceleste.services.models.cold_start_status import ColdStartStatus
from collections.abc import AsyncGenerator


class SystemCheckRepository:
    def __init__(self, system_check_use_case: SystemCheckUseCase):
        """The system check screen's only way to the services, so the screen
        does not know any use case."""
        self.system_check_use_case = system_check_use_case

    async def run_system_check(
        self,
    ) -> AsyncGenerator[tuple[str, ColdStartStatus], None]:
        """Runs cold_start() of every service, one service after another, and
        passes on every status with the service name. One service gives many
        statuses (started, progress, done). This is what really starts the
        services, so it goes to the network, loads models and so on."""
        async for service_name, status in self.system_check_use_case():
            yield service_name, status

    def get_service_names(self) -> list[str]:
        """Names in the order run_system_check() checks them. The screen builds
        one row per name before the check starts."""
        return self.system_check_use_case.service_names
