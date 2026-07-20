from glob import glob
import logging
import os
import shutil

from pydantic import ValidationError
import yaml

from services.models.settings_model import SettingsModel

logger = logging.getLogger(__name__)


class SettingsService:
    def __init__(self) -> None:
        self.settings: SettingsModel | None = None

    def get_settings(self) -> SettingsModel:
        if not self.settings:
            raise RuntimeError(
                "Settings have not been loaded yet. "
                "Or there was an error during loading."
            )

        return self.settings

    def update_settings(self, settings: SettingsModel) -> None:
        config_file = glob("config.yaml")

        if not config_file:
            logger.warning(
                "No config.yaml file found while updating settings. "
                "Creating a new config.yaml from config-example.yaml."
            )
            shutil.copyfile("config-example.yaml", "config.yaml")
            config_file = glob("config.yaml")

        with open(config_file[0], "w") as f:
            yaml.safe_dump(settings.model_dump(), f)

        self.settings = settings

    def load_settings(self) -> None:
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
