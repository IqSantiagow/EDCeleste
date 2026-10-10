import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import (
    FSDJumpEvent,
    LoadedGameEvent,
    FuelScoopEvent,
    ReservoirReplenishedEvent,
    RefuelAllEvent,
    StatusEvent,
    StatusFlags,
)

logger = logging.getLogger(__name__)


class FuelProjection(Projection):
    PROJECTION_STRING = "Current fuel level is: {0}."

    SCOOPING_FUEL_PROJECTION = "Player is currently scooping fuel from a star."

    LOW_FUEL_PROJECTION = "Warning: fuel is low."

    def __init__(self):
        """Everything starts at 0 and False. A fuel level of 0.0 means no fuel
        event has arrived yet, not an empty tank."""
        self.fuel_level = 0.0
        self.fuel_capacity = 0.0
        self.fuel_reservoir = 0.0
        self.is_scooping_fuel = False
        self.is_low_fuel = False

    def process_event(self, event: BaseModel):
        """Tracks the main tank, the tank capacity and the reservoir.

        - FSDJump -> main tank level after the jump.
        - LoadGame -> main tank level and capacity. The only event with the
          capacity.
        - FuelScoop -> main tank level after the scoop.
        - ReservoirReplenished -> main tank and reservoir.
        - RefuelAll -> adds the bought amount, clamped to the capacity.
        - Status (Status.json) -> scooping and low fuel flags, plus both tanks
          when the file has a Fuel block.
        Any other event is skipped.
        """
        if isinstance(event, FSDJumpEvent):
            logger.debug("Received fuel event: %s", event)
            self.fuel_level = event.FuelLevel
            return

        if isinstance(event, LoadedGameEvent):
            logger.debug("Received fuel event: %s", event)
            self.fuel_level = event.FuelLevel
            self.fuel_capacity = event.FuelCapacity
            return

        if isinstance(event, FuelScoopEvent):
            logger.debug("Received fuel event: %s", event)
            # Verified against real journals: Total is the main tank level after
            # the scoop (clamped to FuelCapacity), while Scooped is only the
            # amount gained since the previous FuelScoop event.
            self.fuel_level = event.Total
            return

        if isinstance(event, ReservoirReplenishedEvent):
            logger.debug("Received fuel event: %s", event)
            self.fuel_level = event.FuelMain
            self.fuel_reservoir = event.FuelReservoir
            return

        if isinstance(event, RefuelAllEvent):
            logger.debug("Received fuel event: %s", event)
            # RefuelAll tops the main tank off. Add the purchased amount and, when
            # the capacity is known, clamp to it so a missed LoadGame or drifted
            # level can never push the tracked value past the real tank size.
            self.fuel_level += event.Amount
            if self.fuel_capacity:
                self.fuel_level = min(self.fuel_level, self.fuel_capacity)
            return

        if isinstance(event, StatusEvent):
            logger.debug("Received fuel event: %s", event)
            self.is_scooping_fuel = bool(event.Flags & StatusFlags.ScoopingFuel)
            self.is_low_fuel = bool(event.Flags & StatusFlags.LowFuel)
            if event.Fuel:
                self.fuel_level = event.Fuel.FuelMain
                self.fuel_reservoir = event.Fuel.FuelReservoir
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        """Never empty. The text is, joined with one space:
        1. Always the main tank level, the number of tonnes as the game sends
           it and no unit, e.g. "Current fuel level is: 12.0." The capacity
           and the reservoir never go to the LLM.
        2. "Player is currently scooping fuel from a star." while the scooping
           flag is on.
        3. "Warning: fuel is low." while the low fuel flag is on.
        Before any fuel event the level is still 0.0 and the sentence says
        "0.0", the same as an empty tank. Every call with a level of 0.0 logs
        a warning. No field changes."""
        if self.fuel_level == 0.0:
            logger.warning("Fuel level is at 0. Does the game started?")

        sentences = [self.PROJECTION_STRING.format(self.fuel_level)]

        if self.is_scooping_fuel:
            sentences.append(self.SCOOPING_FUEL_PROJECTION)

        if self.is_low_fuel:
            sentences.append(self.LOW_FUEL_PROJECTION)

        return " ".join(sentences)
