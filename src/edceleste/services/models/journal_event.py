import logging
from enum import Enum
from typing import Annotated, Union

from pydantic import Discriminator, Tag

from edceleste.services.models.game_events import (
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


class JournalEventType(str, Enum):
    LoadGame = "LoadGame"
    StartJump = "StartJump"
    FSDJump = "FSDJump"
    Docked = "Docked"
    Undocked = "Undocked"
    FuelScoop = "FuelScoop"
    DockingGranted = "DockingGranted"
    Location = "Location"
    SupercruiseEntry = "SupercruiseEntry"
    SupercruiseExit = "SupercruiseExit"
    SupercruiseDestinationDrop = "SupercruiseDestinationDrop"
    ApproachBody = "ApproachBody"
    LeaveBody = "LeaveBody"
    ApproachSettlement = "ApproachSettlement"
    ReservoirReplenished = "ReservoirReplenished"
    RefuelAll = "RefuelAll"
    Commander = "Commander"
    Rank = "Rank"
    Promotion = "Promotion"
    Reputation = "Reputation"
    Died = "Died"
    Resurrect = "Resurrect"
    Unknown = "Unknown"


KNOWN_EVENTS: frozenset[JournalEventType] = frozenset(
    event_type
    for event_type in JournalEventType
    if event_type is not JournalEventType.Unknown
)


def event_discriminator(raw: dict) -> JournalEventType:
    event_name = raw.get("event", "")
    try:
        return JournalEventType(event_name)
    except ValueError:
        logger.debug("Received unknown event with name: %s", event_name)
        return JournalEventType.Unknown


JournalEvent = Annotated[
    Union[
        Annotated[LoadedGameEvent, Tag(JournalEventType.LoadGame)],
        Annotated[StartJumpEvent, Tag(JournalEventType.StartJump)],
        Annotated[FSDJumpEvent, Tag(JournalEventType.FSDJump)],
        Annotated[DockedEvent, Tag(JournalEventType.Docked)],
        Annotated[UndockedEvent, Tag(JournalEventType.Undocked)],
        Annotated[FuelScoopEvent, Tag(JournalEventType.FuelScoop)],
        Annotated[DockingGrantedEvent, Tag(JournalEventType.DockingGranted)],
        Annotated[LocationEvent, Tag(JournalEventType.Location)],
        Annotated[SupercruiseEntryEvent, Tag(JournalEventType.SupercruiseEntry)],
        Annotated[SupercruiseExitEvent, Tag(JournalEventType.SupercruiseExit)],
        Annotated[
            SupercruiseDestinationDropEvent,
            Tag(JournalEventType.SupercruiseDestinationDrop),
        ],
        Annotated[ApproachBodyEvent, Tag(JournalEventType.ApproachBody)],
        Annotated[LeaveBodyEvent, Tag(JournalEventType.LeaveBody)],
        Annotated[ApproachSettlementEvent, Tag(JournalEventType.ApproachSettlement)],
        Annotated[
            ReservoirReplenishedEvent, Tag(JournalEventType.ReservoirReplenished)
        ],
        Annotated[RefuelAllEvent, Tag(JournalEventType.RefuelAll)],
        Annotated[CommanderEvent, Tag(JournalEventType.Commander)],
        Annotated[RankEvent, Tag(JournalEventType.Rank)],
        Annotated[PromotionEvent, Tag(JournalEventType.Promotion)],
        Annotated[ReputationEvent, Tag(JournalEventType.Reputation)],
        Annotated[DiedEvent, Tag(JournalEventType.Died)],
        Annotated[ResurrectEvent, Tag(JournalEventType.Resurrect)],
        Annotated[UnknownCheckedEvent, Tag(JournalEventType.Unknown)],
    ],
    Discriminator(event_discriminator),
]
