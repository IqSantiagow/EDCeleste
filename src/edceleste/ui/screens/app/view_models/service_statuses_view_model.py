from dataclasses import dataclass

from edceleste.services.models.service_status import ServiceState, ServiceStatus


@dataclass(slots=True)
class ServiceStatusesViewModel:
    llm: ServiceStatus
    tts: ServiceStatus
    mic: ServiceStatus
    journal: ServiceStatus

    @classmethod
    def empty(cls) -> "ServiceStatusesViewModel":
        """All four services dim with "Not checked yet". The header shows it
        before the first status arrives."""
        not_checked = ServiceStatus(ServiceState.OFF, "Not checked yet")
        return cls(
            llm=not_checked, tts=not_checked, mic=not_checked, journal=not_checked
        )
