from dataclasses import dataclass


@dataclass
class ColdStartStatus:
    service: str
    message: (
        str | None
    )  # If there is a message then service failed, if None then it's good
    is_critical: bool
    completed: bool = False
