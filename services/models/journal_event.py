import logging
from typing import Annotated, Union

from pydantic import Discriminator, BaseModel, Tag

from services.models.game_events import LoadedGameEvent, UnknownCheckedEvent

logger = logging.getLogger(__name__)

KNOWN_EVENTS = ["LoadGame"]


def event_discriminator(raw: dict) -> str:
    event_name = raw.get("event", "")
    if event_name in KNOWN_EVENTS:
        return event_name
    return "Unknown"

def __log_unknown_event(event_name: str)-> None:
    logger.debug("Received unknown event with name: %s", event_name)

LoadedGameEvent = Annotated[LoadedGameEvent, Tag("LoadGame")]

UnknownCheckedEvent = Annotated[UnknownCheckedEvent, Tag("Unknown")]

JournalEvent = Annotated[Union[LoadedGameEvent, UnknownCheckedEvent], Discriminator(event_discriminator)]

