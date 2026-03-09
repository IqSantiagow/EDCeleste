import logging

from pydantic import BaseModel

from projection.event_projections.projection import Projection
from services.models.game_events import FSDJumpEvent, DockedEvent, UndockedEvent, LocationEvent

logger = logging.getLogger(__name__)


class LocationProjection(Projection):
    DOCKED_PROJECTION = "Player is currently docked at station: {0}."

    UNDOCKED_PROJECTION = "Player is currently un-docked from station: {0} flying nearby."

    FSD_TRAVEL_PROJECTION = "Player is currently during the FSD jump to system {0}."

    SYSTEM_LOCATION_PROJECTION = "Player is currently in the {0} system."

    def __init__(self):
        self.current_star_system = None
        self.target_star_system = None
        self.is_docked = False
        self.current_station = None
        self.is_in_fsd_jump = False

    def process_event(self, event: BaseModel) -> None:
        if isinstance(event, FSDJumpEvent):
            logger.debug("Received location event: %s", event)
            self.target_star_system= event.StarSystem
            self.current_station = None
            self.current_star_system=None
            self.is_docked = False
            self.is_in_fsd_jump=True

        if isinstance(event, DockedEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.is_docked = True
            self.current_station = event.StationName

        if isinstance(event, UndockedEvent):
            logger.debug("Received location event: %s", event)
            self.is_docked = False

        if isinstance(event, LocationEvent):
            logger.debug("Received location event: %s", event)
            self.is_docked = event.Docked
            self.current_star_system = event.StarSystem
            self.current_station = event.StationName

    def create_projection(self) -> str:
        projection_string = ""

        if self.current_star_system:
            projection_string += self.SYSTEM_LOCATION_PROJECTION.format(self.current_star_system)

        if self.is_docked:
            projection_string += self.DOCKED_PROJECTION.format(self.current_station)

        if not self.is_docked and self.current_station is not None:
            projection_string+=self.UNDOCKED_PROJECTION.format(self.current_station)

        if self.is_in_fsd_jump:
            projection_string += self.FSD_TRAVEL_PROJECTION.format(self.target_star_system)

        return projection_string
