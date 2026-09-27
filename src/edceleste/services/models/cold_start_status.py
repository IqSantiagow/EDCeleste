from dataclasses import dataclass


@dataclass
class ColdStartStatus:
    service: str
    # If there is a message then service failed (or only warns, see is_warning),
    # if None then it's good
    message: str | None
    is_critical: bool
    completed: bool = False
    # The service works, the message is only a warning for the pilot
    is_warning: bool = False
