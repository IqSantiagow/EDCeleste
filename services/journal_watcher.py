import glob
import logging
import os
import time
from typing import Generator

from pydantic import TypeAdapter

from services.models.journal_event import JournalEvent

logger = logging.getLogger(__name__)


class JournalWatcherService:
    exit_signal = False

    def __init__(self, journal_path):
        self.journal_path = journal_path
        self.adapter = TypeAdapter(JournalEvent)

    def emit_journal_events(self) -> Generator[JournalEvent]:
        self.exit_signal = False

        raw_journal_event = self.__fetch_raw_journal_line()

        for event in raw_journal_event:
            if event: #Check if not empty
                yield self.adapter.validate_json(event)

    def stop_watcher_service(self) -> None:
        self.exit_signal = True

    def __fetch_raw_journal_line(self) -> Generator[str]:
        self.exit_signal = False

        latest_file_path = self.__get_latest_journal_filepath()

        with open(latest_file_path, 'r') as f:
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
        all_files = glob.glob(self.journal_path + '/*.log')

        journal_files = [f for f in all_files if 'Journal' in f]

        if not journal_files:
            raise FileNotFoundError("No journal files found in the specified directory.")

        latest_file = max(journal_files, key=os.path.getctime)

        return latest_file
