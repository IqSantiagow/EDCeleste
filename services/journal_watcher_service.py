import asyncio
import glob
import logging
import os
from typing import AsyncGenerator

from pydantic import TypeAdapter, ValidationError

from services.event_bus import EventBus
from services.models.game_events import GameEvent
from services.models.journal_event import JournalEvent
from services.settings_service import SettingsService
from services.models.settings_model import SettingsIssueModel, SettingsModel

logger = logging.getLogger(__name__)


class JournalWatcherService:
    def __init__(
        self, journal_path: str, event_bus: EventBus, settings_handler: SettingsService
    ) -> None:
        self.__settings_handler = settings_handler
        self.journal_path: str = journal_path
        self.event_bus = event_bus
        self.adapter: TypeAdapter = TypeAdapter(JournalEvent)
        self.exit_signal: bool = False
        self._journal_watcher_task: asyncio.Task | None = None

    def start_watcher_service(self) -> None:
        self.exit_signal = False

        async def watch_journal_task():
            async for event in self.__generate_journal_events():
                await self.event_bus.publish(event)

        self._journal_watcher_task = asyncio.create_task(watch_journal_task())

    def stop_watcher_service(self) -> None:
        self.exit_signal = True
        if self._journal_watcher_task:
            self._journal_watcher_task.cancel()

    def get_journal_healthcheck(self):
        return not self.exit_signal

    async def __generate_journal_events(self) -> AsyncGenerator[GameEvent, None]:
        async for event in self.__fetch_raw_journal_line():
            try:
                yield self.adapter.validate_json(event)
            except ValidationError:
                logger.error("Error during validation for event: %s", event)
                continue

    async def __fetch_raw_journal_line(self) -> AsyncGenerator[str, None]:
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
                yield line.strip()

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
    ) -> list["SettingsIssueModel"]:
        issues = []
        if not new_settings.paths.journal_path:
            issues.append(
                SettingsIssueModel(
                    section=str(self.__class__),
                    field="journal_path",
                    message="Journal path is not set.",
                )
            )

        return issues

    def reload_service(self) -> None:
        new_settings = self.__settings_handler.get_settings()
        self.journal_path = new_settings.paths.journal_path
        self.stop_watcher_service()
        self.start_watcher_service()
