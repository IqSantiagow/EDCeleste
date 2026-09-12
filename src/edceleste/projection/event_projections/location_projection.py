import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import (
    FSDJumpEvent,
    FSDTargetEvent,
    StartJumpEvent,
    DockedEvent,
    UndockedEvent,
    LocationEvent,
    SupercruiseEntryEvent,
    SupercruiseExitEvent,
    SupercruiseDestinationDropEvent,
    ApproachBodyEvent,
    LeaveBodyEvent,
    ApproachSettlementEvent,
)

logger = logging.getLogger(__name__)


class LocationProjection(Projection):
    DOCKED_PROJECTION = "Player is currently docked at station: {0}."

    UNDOCKED_PROJECTION = (
        "Player is currently un-docked from station: {0} flying nearby."
    )

    FSD_TRAVEL_PROJECTION = "Player is currently during the FSD jump to system {0}."

    SYSTEM_LOCATION_PROJECTION = "Player is currently in the {0} system."

    SUPERCRUISE_PROJECTION = "Player is currently in supercruise."

    BODY_PROXIMITY_PROJECTION = "Player is currently near {0}."

    SETTLEMENT_PROJECTION = "Player is close to the settlement: {0}."

    ROUTE_NEXT_HOP_PROJECTION = (
        "Player's next plotted jump is to system {0}, a class {1} star, "
        "with {2} jumps remaining on the route."
    )

    def __init__(self):
        self.current_star_system = None
        self.target_star_system = None
        self.is_docked = False
        self.current_station = None
        self.is_in_fsd_jump = False
        self.is_in_supercruise = False
        self.current_body = None
        self.nearest_settlement = None
        self.route_next_star_system = None
        self.route_next_star_class = None
        self.route_remaining_jumps = None

    def process_event(self, event: BaseModel) -> None:
        if isinstance(event, StartJumpEvent):
            logger.debug("Received location event: %s", event)
            if event.JumpType != "Hyperspace":
                return
            self.target_star_system = event.StarSystem
            self.current_station = None
            self.current_star_system = None
            self.is_docked = False
            self.is_in_fsd_jump = True
            self.is_in_supercruise = False
            self.current_body = None
            self.nearest_settlement = None
            return

        if isinstance(event, FSDTargetEvent):
            logger.debug("Received location event: %s", event)
            self.route_next_star_system = event.Name
            self.route_next_star_class = event.StarClass
            self.route_remaining_jumps = event.RemainingJumpsInRoute
            return

        if isinstance(event, FSDJumpEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.target_star_system = None
            self.is_in_fsd_jump = False
            if event.StarSystem == self.route_next_star_system:
                self.route_next_star_system = None
                self.route_next_star_class = None
                self.route_remaining_jumps = None
            return

        if isinstance(event, DockedEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.is_docked = True
            self.current_station = event.StationName
            self.is_in_fsd_jump = False
            self.is_in_supercruise = False
            self.current_body = None
            self.nearest_settlement = None
            return

        if isinstance(event, UndockedEvent):
            logger.debug("Received location event: %s", event)
            self.is_docked = False
            self.is_in_fsd_jump = False
            return

        if isinstance(event, LocationEvent):
            logger.debug("Received location event: %s", event)
            self.is_docked = event.Docked
            self.current_star_system = event.StarSystem
            self.current_station = event.StationName
            return

        if isinstance(event, SupercruiseEntryEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.is_in_supercruise = True
            self.is_in_fsd_jump = False
            self.is_docked = False
            self.current_station = None
            self.current_body = None
            self.nearest_settlement = None
            return

        if isinstance(event, SupercruiseExitEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.current_body = event.Body
            self.is_in_supercruise = False
            self.is_in_fsd_jump = False
            return

        if isinstance(event, SupercruiseDestinationDropEvent):
            logger.debug("Received location event: %s", event)
            self.is_in_supercruise = False
            return

        if isinstance(event, ApproachBodyEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.current_body = event.Body
            return

        if isinstance(event, LeaveBodyEvent):
            logger.debug("Received location event: %s", event)
            if self.current_body == event.Body:
                self.current_body = None
            self.nearest_settlement = None
            return

        if isinstance(event, ApproachSettlementEvent):
            logger.debug("Received location event: %s", event)
            self.nearest_settlement = event.Name
            if event.BodyName:
                self.current_body = event.BodyName
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        projection_string = ""

        if self.current_star_system:
            projection_string += self.SYSTEM_LOCATION_PROJECTION.format(
                self.current_star_system
            )

        if self.is_docked:
            projection_string += self.DOCKED_PROJECTION.format(self.current_station)

        if not self.is_docked and self.current_station is not None:
            projection_string += self.UNDOCKED_PROJECTION.format(self.current_station)

        if self.is_in_supercruise:
            projection_string += self.SUPERCRUISE_PROJECTION

        if self.current_body:
            projection_string += self.BODY_PROXIMITY_PROJECTION.format(
                self.current_body
            )

        if self.nearest_settlement:
            projection_string += self.SETTLEMENT_PROJECTION.format(
                self.nearest_settlement
            )

        if self.is_in_fsd_jump:
            projection_string += self.FSD_TRAVEL_PROJECTION.format(
                self.target_star_system
            )

        if self.route_next_star_system:
            projection_string += self.ROUTE_NEXT_HOP_PROJECTION.format(
                self.route_next_star_system,
                self.route_next_star_class,
                self.route_remaining_jumps,
            )

        return projection_string
