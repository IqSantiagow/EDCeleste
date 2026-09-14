import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import LoadoutEvent

logger = logging.getLogger(__name__)

FRAME_SHIFT_DRIVE_SLOT = "FrameShiftDrive"


class LoadoutProjection(Projection):
    HULL_HEALTH_PROJECTION = "Ship hull health is at {0:.0%}."

    def __init__(self):
        self.hull_health = 1.0
        self.unladen_mass = 0.0
        self.cargo_capacity = 0
        self.max_jump_range = 0.0
        self.rebuy_cost = 0
        self.fsd_module_item = None
        self.are_all_modules_healthy = True

    def process_event(self, event: BaseModel) -> None:
        if isinstance(event, LoadoutEvent):
            logger.debug("Received loadout event: %s", event)
            self.hull_health = event.HullHealth
            self.unladen_mass = event.UnladenMass
            self.cargo_capacity = event.CargoCapacity
            self.max_jump_range = event.MaxJumpRange
            self.rebuy_cost = event.Rebuy
            self.are_all_modules_healthy = all(
                module.Health >= 1.0 for module in event.Modules
            )
            frame_shift_drive = next(
                (
                    module
                    for module in event.Modules
                    if module.Slot == FRAME_SHIFT_DRIVE_SLOT
                ),
                None,
            )
            self.fsd_module_item = frame_shift_drive.Item if frame_shift_drive else None
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        return self.HULL_HEALTH_PROJECTION.format(self.hull_health)
