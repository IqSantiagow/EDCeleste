import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import (
    FSDJumpEvent,
    FSDTargetEvent,
    StartJumpEvent,
    DockedEvent,
    DockingGrantedEvent,
    UndockedEvent,
    LocationEvent,
    SupercruiseEntryEvent,
    SupercruiseExitEvent,
    SupercruiseDestinationDropEvent,
    ApproachBodyEvent,
    LeaveBodyEvent,
    ApproachSettlementEvent,
    StatusEvent,
    StatusFlags,
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

    LANDING_PAD_PROJECTION = "Player was assigned landing pad {0} at station {1}."

    SUPERCRUISE_DROP_PROJECTION = "Player dropped out of supercruise at {0}."

    ROUTE_NEXT_HOP_PROJECTION = (
        "Player's next plotted jump is to system {0}, a class {1} star, "
        "with {2} jumps remaining on the route."
    )

    def __init__(self):
        """Everything starts as None or False, which means "not known yet"."""
        self.current_star_system = None
        self.target_star_system = None
        self.is_docked = False
        self.current_station = None
        self.is_in_fsd_jump = False
        self.is_in_supercruise = False
        self.current_body = None
        self.nearest_settlement = None
        self.assigned_landing_pad = None
        self.assigned_landing_pad_station = None
        self.supercruise_drop_place = None
        self.route_next_star_system = None
        self.route_next_star_class = None
        self.route_remaining_jumps = None
        self.system_security_level = None
        self.system_allegiance = None
        self.system_government = None
        self.system_economy = None
        self.system_second_economy = None
        self.system_population = None

    def process_event(self, event: BaseModel) -> None:
        """Tracks where the ship is: system, station, body, settlement, landing
        pad, supercruise drop place, the next hop of the route and the system
        facts (security, allegiance, government, economy, population).

        - Status (Status.json) -> docked, supercruise and FSD jump flags.
        - StartJump -> only for Hyperspace (supercruise charging is skipped).
          Remembers the target system and forgets the current system,
          station, body, settlement, drop place and landing pad.
        - FSDTarget -> next hop of the plotted route.
        - FSDJump -> new current system and its facts. Clears the target
          system, and the route hop when we arrived at it.
        - Docked -> system and station. Clears body, settlement, drop place.
        - DockingGranted -> landing pad and its station.
        - Undocked -> forgets the landing pad. The station stays, so the
          prompt can say "flying nearby".
        - Location -> system and station. System facts are updated only when
          the event has them, a blank value keeps the old one.
        - SupercruiseEntry -> system. Forgets station, body, settlement, drop
          place and landing pad.
        - SupercruiseExit -> system and body.
        - SupercruiseDestinationDrop -> readable drop place.
        - ApproachBody -> system and body.
        - LeaveBody -> clears the body (only when it is the one we left) and
          the settlement.
        - ApproachSettlement -> settlement, and the body when the event has it.
        Any other event is skipped.
        """
        if isinstance(event, StatusEvent):
            logger.debug("Received location event: %s", event)
            self.is_docked = bool(event.Flags & StatusFlags.Docked)
            self.is_in_supercruise = bool(event.Flags & StatusFlags.Supercruise)
            self.is_in_fsd_jump = bool(event.Flags & StatusFlags.FsdJump)
            return

        if isinstance(event, StartJumpEvent):
            logger.debug("Received location event: %s", event)
            if event.JumpType != "Hyperspace":
                return
            self.target_star_system = event.StarSystem
            self.current_star_system = None
            self.current_station = None
            self.current_body = None
            self.nearest_settlement = None
            self.supercruise_drop_place = None
            self.__forget_landing_pad()
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
            self.system_security_level = event.SystemSecurity_Localised
            self.system_allegiance = event.SystemAllegiance
            self.system_government = event.SystemGovernment_Localised
            self.system_economy = event.SystemEconomy_Localised
            self.system_second_economy = event.SystemSecondEconomy_Localised
            self.system_population = event.Population
            if event.StarSystem == self.route_next_star_system:
                self.route_next_star_system = None
                self.route_next_star_class = None
                self.route_remaining_jumps = None
            return

        if isinstance(event, DockedEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.current_station = event.StationName
            self.current_body = None
            self.nearest_settlement = None
            self.supercruise_drop_place = None
            return

        if isinstance(event, DockingGrantedEvent):
            logger.debug("Received location event: %s", event)
            self.assigned_landing_pad = event.LandingPad
            self.assigned_landing_pad_station = event.StationName
            return

        if isinstance(event, UndockedEvent):
            logger.debug("Received location event: %s", event)
            self.__forget_landing_pad()
            return

        if isinstance(event, LocationEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.current_station = event.StationName
            # These fields are only sent by the game when known, so skip a
            # blank value rather than clobbering the last good reading.
            if event.SystemSecurity_Localised:
                self.system_security_level = event.SystemSecurity_Localised
            if event.SystemAllegiance:
                self.system_allegiance = event.SystemAllegiance
            if event.SystemGovernment_Localised:
                self.system_government = event.SystemGovernment_Localised
            if event.SystemEconomy_Localised:
                self.system_economy = event.SystemEconomy_Localised
            if event.SystemSecondEconomy_Localised:
                self.system_second_economy = event.SystemSecondEconomy_Localised
            if event.Population is not None:
                self.system_population = event.Population
            return

        if isinstance(event, SupercruiseEntryEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.current_station = None
            self.current_body = None
            self.nearest_settlement = None
            self.supercruise_drop_place = None
            self.__forget_landing_pad()
            return

        if isinstance(event, SupercruiseExitEvent):
            logger.debug("Received location event: %s", event)
            self.current_star_system = event.StarSystem
            self.current_body = event.Body
            return

        if isinstance(event, SupercruiseDestinationDropEvent):
            logger.debug("Received location event: %s", event)
            # Type_Localised is missing when the destination has a plain name,
            # e.g. a station.
            self.supercruise_drop_place = event.Type_Localised or event.Type
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
        """Adds one sentence for every known fact and skips the unknown ones,
        so the text is empty before the first location event. A station while
        not docked becomes "un-docked from ... flying nearby". The system facts
        are not in the text, only the dashboard shows them."""
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

        if self.assigned_landing_pad is not None:
            projection_string += self.LANDING_PAD_PROJECTION.format(
                self.assigned_landing_pad, self.assigned_landing_pad_station
            )

        if self.supercruise_drop_place:
            projection_string += self.SUPERCRUISE_DROP_PROJECTION.format(
                self.supercruise_drop_place
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

    def __forget_landing_pad(self) -> None:
        """A landing pad is only valid until we undock or leave for supercruise
        or hyperspace."""
        self.assigned_landing_pad = None
        self.assigned_landing_pad_station = None
