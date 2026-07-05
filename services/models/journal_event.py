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
    SupercruiseEntryEvent,
    SupercruiseExitEvent,
    SupercruiseDestinationDropEvent,
    ApproachBodyEvent,
    LeaveBodyEvent,
    ApproachSettlementEvent,
    ReservoirReplenishedEvent,
    RefuelAllEvent,
    CommanderEvent,
    RankEvent,
    PromotionEvent,
    ReputationEvent,
    DiedEvent,
    ResurrectEvent,
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
        "SupercruiseEntry",
        "SupercruiseExit",
        "SupercruiseDestinationDrop",
        "ApproachBody",
        "LeaveBody",
        "ApproachSettlement",
        "ReservoirReplenished",
        "RefuelAll",
        "Commander",
        "Rank",
        "Promotion",
        "Reputation",
        "Died",
        "Resurrect",
    ]
)


def event_discriminator(raw: dict) -> str:
    event_name = raw.get("event", "")
    if event_name in KNOWN_EVENTS:
        return event_name
    logger.debug("Received unknown event with name: %s", event_name)
    return "Unknown"


_JournalEvent = Annotated[
    Union[
        Annotated[LoadedGameEvent, Tag("LoadGame")],
        Annotated[StartJumpEvent, Tag("StartJump")],
        Annotated[FSDJumpEvent, Tag("FSDJump")],
        Annotated[DockedEvent, Tag("Docked")],
        Annotated[UndockedEvent, Tag("Undocked")],
        Annotated[FuelScoopEvent, Tag("FuelScoop")],
        Annotated[DockingGrantedEvent, Tag("DockingGranted")],
        Annotated[LocationEvent, Tag("Location")],
        Annotated[SupercruiseEntryEvent, Tag("SupercruiseEntry")],
        Annotated[SupercruiseExitEvent, Tag("SupercruiseExit")],
        Annotated[SupercruiseDestinationDropEvent, Tag("SupercruiseDestinationDrop")],
        Annotated[ApproachBodyEvent, Tag("ApproachBody")],
        Annotated[LeaveBodyEvent, Tag("LeaveBody")],
        Annotated[ApproachSettlementEvent, Tag("ApproachSettlement")],
        Annotated[ReservoirReplenishedEvent, Tag("ReservoirReplenished")],
        Annotated[RefuelAllEvent, Tag("RefuelAll")],
        Annotated[CommanderEvent, Tag("Commander")],
        Annotated[RankEvent, Tag("Rank")],
        Annotated[PromotionEvent, Tag("Promotion")],
        Annotated[ReputationEvent, Tag("Reputation")],
        Annotated[DiedEvent, Tag("Died")],
        Annotated[ResurrectEvent, Tag("Resurrect")],
        Annotated[UnknownCheckedEvent, Tag("Unknown")],
    ],
    Discriminator(event_discriminator),
]
