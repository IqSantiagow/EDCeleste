import logging
from typing import Annotated, Union

from pydantic import Discriminator, Tag

from services.models.game_events import (
    LoadedGameEvent,
    UnknownCheckedEvent,
    StartJumpEvent,
    FSDJumpEvent,
    DockedEvent,
    UndockedEvent,
    FuelScoopEvent,
    DockingGrantedEvent,
    LocationEvent,
)

logger = logging.getLogger(__name__)

KNOWN_EVENTS: frozenset[str] = frozenset(
    [
        "LoadGame",
        "StartJump",
        "FSDJump",
        "Docked",
        "Undocked",
        "FuelScoop",
        "DockingGranted",
        "Location",
    ]
)


def event_discriminator(raw: dict) -> str:
    event_name = raw.get("event", "")
    if event_name in KNOWN_EVENTS:
        return event_name
    logger.debug("Received unknown event with name: %s", event_name)
    return "Unknown"


JournalEvent = Annotated[
    Union[
        Annotated[LoadedGameEvent, Tag("LoadGame")],
        Annotated[StartJumpEvent, Tag("StartJump")],
        Annotated[FSDJumpEvent, Tag("FSDJump")],
        Annotated[DockedEvent, Tag("Docked")],
        Annotated[UndockedEvent, Tag("Undocked")],
        Annotated[FuelScoopEvent, Tag("FuelScoop")],
        Annotated[DockingGrantedEvent, Tag("DockingGranted")],
        Annotated[LocationEvent, Tag("Location")],
        Annotated[UnknownCheckedEvent, Tag("Unknown")],
    ],
    Discriminator(event_discriminator),
]
