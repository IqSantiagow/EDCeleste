from dataclasses import dataclass
from functools import singledispatchmethod

from services.models.game_events import (
    DockedEvent,
    GameEvent,
    LoadedGameEvent,
    StartJumpEvent,
)


@dataclass(slots=True)
class JournalLogViewModel:
    timestamp: str
    event: str
    details: str

    @classmethod
    def empty(cls) -> "JournalLogViewModel":
        return cls(timestamp="", event="", details="")

    @singledispatchmethod
    @classmethod
    def from_event(cls, event: GameEvent) -> "JournalLogViewModel":
        return cls(
            timestamp=str(event.timestamp),
            event=event.model_dump().get("event", "Unknown"),
            details="Unknown event type: " + str(event.__class__.__name__),
        )

    @from_event.register(LoadedGameEvent)
    @classmethod
    def _1(cls, event: LoadedGameEvent) -> "JournalLogViewModel":
        return cls(
            timestamp=str(event.timestamp),
            event=event.event,
            details=f"Commander: {event.Commander}, Ship: {event.Ship}, "
            f"Credits: {event.Credits}",
        )

    @from_event.register(StartJumpEvent)
    @classmethod
    def _2(cls, event: StartJumpEvent) -> "JournalLogViewModel":
        # StarSystem/SystemAddress are only present for the "Hyperspace"
        # variant; the "Supercruise" variant omits them, so skip missing fields.
        parts = [f"JumpType: {event.JumpType}"]
        if event.StarSystem is not None:
            parts.append(f"StarSystem: {event.StarSystem}")
        if event.SystemAddress is not None:
            parts.append(f"SystemAddress: {event.SystemAddress}")
        return cls(
            timestamp=str(event.timestamp),
            event=event.event,
            details=", ".join(parts),
        )

    @from_event.register(DockedEvent)
    @classmethod
    def _3(cls, event: DockedEvent) -> "JournalLogViewModel":
        return cls(
            timestamp=str(event.timestamp),
            event=event.event,
            details=f"StarSystem: {event.StarSystem}, "
            f"StationName: {event.StationName}, "
            f"StationType: {event.StationType}",
        )
