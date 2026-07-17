from glob import glob
import shutil
import os
import logging
import yaml

from pydantic import ValidationError

from services.event_bus import EventBus
from services.models.settings_model import (
    NewServiceEvent,
    SettingsChangedEvent,
    SettingsModel,
)

logger = logging.getLogger(__name__)


class SettingsService:
    settings: SettingsModel | None = None

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.event_bus.subscribe(NewServiceEvent, self.handle_new_service_event)

    async def handle_new_service_event(self, event: NewServiceEvent) -> None:
        if not self.settings:
            logger.warning(
                "Settings have not been loaded yet. Cannot handle new service event."
            )
            return

        await self.event_bus.publish(SettingsChangedEvent(self.settings))

    def get_settings(self) -> SettingsModel:
        if not self.settings:
            raise RuntimeError(
                "Settings have not been loaded yet. "
                "Or there was an error during loading."
            )

        return self.settings

    async def update_settings(self, settings: SettingsModel) -> None:
        changed_sections = [
            section
            for section in settings.model_dump().keys()
            if getattr(settings, section) != getattr(self.settings, section)
        ]

        if len(changed_sections) > 1:
            raise RuntimeError("Multiple settings sections changed.")

        if not changed_sections:
            return

        self.settings = settings

        config_file = glob("config.yaml")

        if not config_file:
            logger.warning(
                "No config.yaml file found while updating settings. "
                "Creating a new config.yaml from config-example.yaml."
            )
            shutil.copyfile("config-example.yaml", "config.yaml")

        with open(config_file[0], "w") as f:
            yaml.safe_dump(self.settings.model_dump(), f)

        await self.event_bus.publish(SettingsChangedEvent(self.settings))

    async def load_settings(self) -> None:
        config_file = glob("config.yaml")

        if not config_file:
            shutil.copyfile("config-example.yaml", "config.yaml")

            if not os.path.exists("config.yaml"):
                raise RuntimeError("Failed to copy config-example.yaml to config.yaml.")

            raise FileNotFoundError(
                "No config.yaml file found in the current directory. File has been "
                "created from config-example.yaml. Please edit it and restart the "
                "application."
            )

        with open(config_file[0]) as f:
            data = yaml.safe_load(f)

        try:
            self.settings = SettingsModel.model_validate(data)
            logger.info("Settings loaded successfully from config.yaml.")
        except ValidationError as e:
            logger.error("Failed to load settings from config.yaml.", exc_info=e)
            raise RuntimeError("Failed to load settings from config.yaml.") from e

        await self.event_bus.publish(SettingsChangedEvent(self.settings))
