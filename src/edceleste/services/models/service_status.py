from dataclasses import dataclass
from enum import StrEnum


class ServiceState(StrEnum):
    OK = "ok"
    OFF = "off"
    ERROR = "error"


@dataclass
class ServiceStatus:
    state: ServiceState
    reason: str  # plain words, the header shows it in a tooltip
