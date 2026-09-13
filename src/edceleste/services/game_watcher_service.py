import asyncio
import glob
import logging
import os
from typing import AsyncGenerator

from pydantic import TypeAdapter, ValidationError

from edceleste.services.event_bus import EventBus
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.game_events import StatusEvent
from edceleste.services.models.journal_event import JournalEvent
from edceleste.services.settings_service import SettingsService
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel

logger = logging.getLogger(__name__)


class GameWatcherService:
    def __init__(
        self, journal_path: str, event_bus: EventBus, settings_handler: SettingsService
    ) -> None:
        self.__settings_handler = settings_handler
        self.journal_path: str = journal_path
        self.event_bus = event_bus
        self.adapter: TypeAdapter = TypeAdapter(JournalEvent)
        self.exit_signal: bool = False
        self._game_watcher_tasks: list[asyncio.Task] = []

    def start_watcher_service(self) -> None:
        self.exit_signal = False
        self._game_watcher_tasks.append(
            asyncio.create_task(self.__generate_journal_events())
        )
        self._game_watcher_tasks.append(
            asyncio.create_task(self.watch_status_file_and_generate_event())
        )

    def stop_watcher_service(self) -> None:
        self.exit_signal = True
        if self._game_watcher_tasks:
            for task in self._game_watcher_tasks:
                task.cancel()
            self._game_watcher_tasks.clear()

    async def __generate_journal_events(self) -> None:
        latest_file_path = self.__get_latest_journal_filepath()

        with open(latest_file_path, "r") as f:
            f.seek(0, 2)
            while True:
                if self.exit_signal:
                    break
                line = f.readline()
                if not line:
                    await asyncio.sleep(0.1)
                    continue
                try:
                    event = self.adapter.validate_json(line.strip())
                    await self.event_bus.publish(event)
                except ValidationError:
                    logger.error("Error during validation for event: %s", line)
                    continue

    def __get_latest_journal_filepath(self) -> str:
        all_files = glob.glob(self.journal_path + "/*.log")

        journal_files = [f for f in all_files if "Journal" in f]

        if not journal_files:
            self.exit_signal = True
            raise FileNotFoundError(
                "No journal files found in the specified directory."
            )

        latest_file = max(journal_files, key=os.path.getmtime)

        return latest_file

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        if not new_settings.paths.journal_path or new_settings.paths.journal_path == "":
            return SettingsIssueModel(
                section="paths",
                field="journal_path",
                message="Journal path is not set.",
            )
        if not os.path.isdir(new_settings.paths.journal_path):
            return SettingsIssueModel(
                section="paths",
                field="journal_path",
                message=(
                    f"Journal path '{new_settings.paths.journal_path}' does not exist."
                ),
            )
        if not glob.glob(new_settings.paths.journal_path + "/*.log"):
            return SettingsIssueModel(
                section="paths",
                field="journal_path",
                message=(
                    "No journal log files found in "
                    f"'{new_settings.paths.journal_path}'."
                ),
            )
        return None

    def reload_service(self) -> None:
        new_settings = self.__settings_handler.get_settings()
        self.journal_path = new_settings.paths.journal_path
        self.stop_watcher_service()
        self.start_watcher_service()

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        status = ColdStartStatus(
            service="journal_watcher",
            message=None,
            is_critical=True,
            completed=False,
        )
        yield status

        try:
            self.reload_service()
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status

    async def watch_status_file_and_generate_event(self) -> None:
        status_file_path = os.path.join(self.journal_path, "Status.json")
        last_modified_time = None
        while True:
            if self.exit_signal:
                break

            if not os.path.isfile(status_file_path):
                logger.warning(
                    "Status file not found at '%s'. Waiting for it to appear...",
                    status_file_path,
                )
                await asyncio.sleep(1)
                continue

            current_modified_time = os.path.getmtime(status_file_path)
            if current_modified_time != last_modified_time:
                last_modified_time = current_modified_time
                with open(status_file_path, "r") as f:
                    line = f.read()
                    if line:
                        try:
                            status_data = StatusEvent.model_validate_json(line)
                            await self.event_bus.publish(status_data)
                        except ValidationError:
                            logger.error(
                                "Error during validation for status event: %s", line
                            )

            await asyncio.sleep(1)
