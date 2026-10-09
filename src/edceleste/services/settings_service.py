from collections.abc import AsyncGenerator
import logging
from pathlib import Path
import shutil

from pydantic import ValidationError
import yaml

from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.settings_model import SettingsModel

logger = logging.getLogger(__name__)


class SettingsService:
    def __init__(
        self,
        config_path: Path = Path("config.yaml"),
        example_config_path: Path = Path("config-example.yaml"),
    ) -> None:
        """Does not read any file. The settings stay None until load_settings()
        runs. The container calls it right away, before any other service is
        built."""
        # Tests point these at a temp folder, so the real config.yaml stays untouched
        self.config_path = config_path
        self.example_config_path = example_config_path
        self.settings: SettingsModel | None = None

    def get_settings(self) -> SettingsModel:
        """Gives the settings kept in memory, it does not read the file again.
        Raises RuntimeError when load_settings() has not run yet or failed."""
        if not self.settings:
            raise RuntimeError(
                "Settings have not been loaded yet. "
                "Or there was an error during loading."
            )

        return self.settings

    def save_settings(self, settings: SettingsModel) -> None:
        """Writes the settings to config.yaml and then keeps them in memory, so
        get_settings() gives the new ones right away.

        1. When config.yaml is missing, copies config-example.yaml to it first.
           Raises RuntimeError when the copy did not appear.
        2. Overwrites the whole config.yaml with the new settings as YAML.
           Comments in the file are lost.
        3. Replaces the settings in memory.
        It does not reload the other services, the caller does that.
        """
        if not self.config_path.exists():
            logger.warning(
                "No config.yaml file found while updating settings. "
                "Creating a new config.yaml from config-example.yaml."
            )
            shutil.copyfile(self.example_config_path, self.config_path)
            if not self.config_path.exists():
                raise RuntimeError(
                    "Failed to create config.yaml from config-example.yaml."
                )

        with self.config_path.open("w") as f:
            yaml.safe_dump(settings.model_dump(), f)

        self.settings = settings

    def load_settings(self) -> None:
        """Reads config.yaml from disk into memory.

        1. When config.yaml is missing, copies config-example.yaml to it and
           raises FileNotFoundError asking the pilot to edit it and restart.
           RuntimeError when even the copy did not appear.
        2. Reads the YAML and validates it as SettingsModel.
        3. A file that does not match the model raises RuntimeError and the old
           settings in memory stay as they were. A broken YAML file raises the
           yaml error as it is.
        """
        if not self.config_path.exists():
            shutil.copyfile(self.example_config_path, self.config_path)

            if not self.config_path.exists():
                raise RuntimeError("Failed to copy config-example.yaml to config.yaml.")

            raise FileNotFoundError(
                "No config.yaml file found in the current directory. File has been "
                "created from config-example.yaml. Please edit it and restart the "
                "application."
            )

        with self.config_path.open("r") as f:
            data = yaml.safe_load(f)

        try:
            self.settings = SettingsModel.model_validate(data)
            logger.info("Settings loaded successfully from config.yaml.")
        except ValidationError as e:
            logger.error("Failed to load settings from config.yaml.", exc_info=e)
            raise RuntimeError("Failed to load settings from config.yaml.") from e

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Reads config.yaml again (load_settings).
        3. Yields the status again with completed=True, and the error text in
           message when reading failed.
        Never raises. It is critical: when it fails the system check stops and
        the dashboard does not open.
        """
        status = ColdStartStatus(
            service="settings",
            message=None,
            is_critical=True,
            completed=False,
        )
        yield status

        try:
            self.load_settings()
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status
