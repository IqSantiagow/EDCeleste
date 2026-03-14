import glob
import logging
import os
import time
from typing import Generator

from pydantic import TypeAdapter, ValidationError

from services.event_bus import EventBus
from services.models.game_events import GameEvent
from services.models.journal_event import _JournalEvent

logger = logging.getLogger(__name__)


class JournalWatcherService:
    def __init__(self, journal_path: str, event_bus: EventBus):
        self.journal_path: str = journal_path
        self.event_bus: EventBus = event_bus
        self.adapter: TypeAdapter = TypeAdapter(_JournalEvent)
        self.exit_signal: bool = False

    def start_watcher_service(self):
        self.exit_signal = False
        for event in self.__generate_journal_events():
            self.event_bus.publish(event)

    def stop_watcher_service(self) -> None:
        self.exit_signal = True

    def __generate_journal_events(self) -> Generator[GameEvent]:
        raw_journal_event = self.__fetch_raw_journal_line()

        for event in raw_journal_event:
            try:
                yield self.adapter.validate_json(event)
            except ValidationError:
                logger.error("Error during validation for event: %s", event)
                continue

    def __fetch_raw_journal_line(self) -> Generator[str]:
        latest_file_path = self.__get_latest_journal_filepath()

        with open(latest_file_path, "r") as f:
            f.seek(0, 2)
            while True:
                if self.exit_signal:
                    break
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                yield line.strip()

    def __get_latest_journal_filepath(self) -> str:
        all_files = glob.glob(self.journal_path + "/*.log")

        journal_files = [f for f in all_files if "Journal" in f]

        if not journal_files:
            raise FileNotFoundError(
                "No journal files found in the specified directory."
            )

        latest_file = max(journal_files, key=os.path.getmtime)

        return latest_file
