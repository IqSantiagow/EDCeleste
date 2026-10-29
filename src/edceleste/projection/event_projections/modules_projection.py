import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import (
    ModuleInfoEvent,
    ModuleInfoItemModel,
)

logger = logging.getLogger(__name__)


class ModulesProjection(Projection):
    MODULES_PROJECTION = "Ship modules (slot: module, power draw, power priority): {0}."

    def __init__(self):
        """modules stays an empty list until ModulesInfo.json is read. There is
        no separate flag: a file without modules and a file not yet read both
        give an empty list, and both say nothing to the LLM."""
        self.modules: list[ModuleInfoItemModel] = []

    def process_event(self, event: BaseModel) -> None:
        """Only the ModuleInfo event (ModulesInfo.json, rewritten by the game
        when the power of the modules changes) counts. The whole list replaces
        the old one. Any other event is skipped. Returns nothing, raises
        nothing."""
        if isinstance(event, ModuleInfoEvent):
            logger.debug("Received modules event: %s", event)
            self.modules = event.Modules
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        """Empty string while the list of modules is empty (the file was not
        read yet, or it has no modules). Otherwise one sentence with every
        module in the order of the file, separated by "; ", like
        "MainEngines: int_engine_size4_class1, 3.28 MW, priority 0". The
        priority is the number from the file, so 0 is written as "priority 0".
        It is left out only for a module that has none (None). Reads the fields
        only, raises nothing."""
        if not self.modules:
            return ""

        return self.MODULES_PROJECTION.format(
            "; ".join(
                self.__module_to_slot_item_power_priority_text(module)
                for module in self.modules
            )
        )

    def __module_to_slot_item_power_priority_text(
        self, module: ModuleInfoItemModel
    ) -> str:
        """One module as "slot: module, <power draw> MW", with ", priority N"
        added when the module has a priority. The power draw is written
        without trailing zeros (3.28, 0.6, and 0 for no draw). Priority 0 is
        a priority and is written. Reads the module only."""
        text = f"{module.Slot}: {module.Item}, {module.Power:g} MW"
        if module.Priority is not None:
            text += f", priority {module.Priority}"
        return text
