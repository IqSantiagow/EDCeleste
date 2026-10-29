import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import CargoEvent, CargoItemModel

logger = logging.getLogger(__name__)


class CargoProjection(Projection):
    CARGO_PROJECTION = "Cargo hold contains: {0}."

    EMPTY_CARGO_PROJECTION = "Cargo hold is empty."

    def __init__(self):
        """inventory starts as an empty list and has_read_cargo_file as False.
        The flag turns True when Cargo.json is read: before that the cargo is
        not known, which is not the same as an empty hold."""
        self.has_read_cargo_file = False
        self.inventory: list[CargoItemModel] = []

    def process_event(self, event: BaseModel) -> None:
        """Only the Cargo event (Cargo.json, rewritten by the game on every
        change of the hold) counts. The whole inventory replaces the old one
        (it never adds to it), also when the new one is empty, and the cargo
        counts as known from now on. Any other event is skipped. Returns
        nothing, raises nothing."""
        if isinstance(event, CargoEvent):
            logger.debug("Received cargo event: %s", event)
            self.has_read_cargo_file = True
            self.inventory = event.Inventory
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        """Empty string until Cargo.json has been read. After that either
        "Cargo hold is empty." or "Cargo hold contains: " followed by every
        commodity with its tonnes, like "5 t Gold, 2 t Water", in the order of
        the file. The name is the localised one, or the raw game name when the
        file has no localised one. Reads the fields only, raises nothing."""
        if not self.has_read_cargo_file:
            return ""

        if not self.inventory:
            return self.EMPTY_CARGO_PROJECTION

        return self.CARGO_PROJECTION.format(
            ", ".join(
                f"{item.Count} t {item.Name_Localised or item.Name}"
                for item in self.inventory
            )
        )
