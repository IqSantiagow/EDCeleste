import asyncio
import glob
import logging
import os
from typing import AsyncGenerator

from pydantic import TypeAdapter, ValidationError

from edceleste.services.event_bus import EventBus
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.game_events import MarketEvent, StatusEvent
from edceleste.services.models.journal_event import JournalEvent
from edceleste.services.settings_service import SettingsService
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel

logger = logging.getLogger(__name__)


def find_journal_files(folder: str) -> list[str]:
    """Lists the files named Journal*.log that lie directly in the folder.
    Reads the disk, changes nothing and never raises.

    Returns the full path of every file, in no guaranteed order, not sorted
    by time. Only the file name is matched, never the folder path: a folder
    called "MyJournals" does not turn its app.log into a journal. Characters
    of the folder path that glob treats as a pattern, like "[", are taken
    literally. An empty list means there is no journal file, or the folder
    does not exist or cannot be read.

    Both the settings check and the watcher use this one rule, so a folder that
    passes the check can always be watched."""
    return glob.glob(os.path.join(glob.escape(folder), "Journal*.log"))


class GameWatcherService:
    def __init__(
        self, journal_path: str, event_bus: EventBus, settings_service: SettingsService
    ) -> None:
        """Only stores the dependencies, no file is opened and no task is
        started. Watching starts in reload_service(), during cold_start() or
        after the settings change."""
        self.__settings_service = settings_service
        self.journal_path: str = journal_path
        self.event_bus = event_bus
        self.adapter: TypeAdapter = TypeAdapter(JournalEvent)
        self.exit_signal: bool = False
        self._game_watcher_tasks: list[asyncio.Task] = []

    def start_watcher_service(self) -> None:
        """Starts three asyncio tasks on the running loop, each publishes game
        events on the event bus:
        1. new lines of the newest Journal*.log file,
        2. Status.json,
        3. Market.json.
        Raises FileNotFoundError, before any task starts, when journal_path has
        no journal file. The journal file is picked only here, a new journal
        file written later by the game is not followed.
        """
        latest_journal_file_path = self.__get_latest_journal_filepath()

        self.exit_signal = False
        self._game_watcher_tasks.append(
            asyncio.create_task(
                self.__publish_new_journal_lines(latest_journal_file_path)
            )
        )
        self._game_watcher_tasks.append(
            asyncio.create_task(self.watch_status_file_and_publish_event())
        )
        self._game_watcher_tasks.append(
            asyncio.create_task(self.watch_market_file_and_publish_event())
        )

    def stop_watcher_service(self) -> None:
        """Sets exit_signal, so the watch loops end, and cancels all watcher
        tasks. Safe to call when nothing is running."""
        self.exit_signal = True
        if self._game_watcher_tasks:
            for task in self._game_watcher_tasks:
                task.cancel()
            self._game_watcher_tasks.clear()

    async def __publish_new_journal_lines(self, journal_file_path: str) -> None:
        """Follows the journal file like "tail -f" until exit_signal is set.

        1. Jumps to the end of the file, so lines written before the start are
           skipped.
        2. Checks for a new line every 0.1 s.
        3. Parses every new line as a JournalEvent (unknown events become
           UnknownCheckedEvent) and publishes it on the event bus.
        A line that does not parse is logged and skipped.
        """
        with open(journal_file_path, "r") as f:
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
        """Looks in the folder self.journal_path and returns the full path of
        the Journal*.log file (see find_journal_files) that was modified last.
        Reads the disk.

        When the folder has no such file, it sets exit_signal (so this is not a
        pure getter) and raises FileNotFoundError. Only start_watcher_service
        calls it."""
        journal_files = find_journal_files(self.journal_path)

        if not journal_files:
            self.exit_signal = True
            raise FileNotFoundError(f"No journal files found in '{self.journal_path}'.")

        latest_file = max(journal_files, key=os.path.getmtime)

        return latest_file

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Checks the journal path of new settings before they are saved. Reads
        the disk, changes no state and never raises.

        Checks in order and returns the first issue:
        1. the path is set (not empty),
        2. the folder exists,
        3. the folder has at least one Journal*.log file (find_journal_files),
           the same rule the watcher uses to start.
        The issue points at section "paths" and field "journal_path", and its
        message is the text the settings screen shows next to the path.
        Returns None when everything is fine.
        """
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
        if not find_journal_files(new_settings.paths.journal_path):
            return SettingsIssueModel(
                section="paths",
                field="journal_path",
                message=(
                    "No Elite Dangerous journal files (Journal*.log) found in "
                    f"'{new_settings.paths.journal_path}'."
                ),
            )
        return None

    def reload_service(self) -> None:
        """Takes the journal path from the current settings, stops the running
        watcher tasks and starts new ones. Raises FileNotFoundError when the
        new path has no journal file, then nothing is watched."""
        new_settings = self.__settings_service.get_settings()
        self.journal_path = new_settings.paths.journal_path
        self.stop_watcher_service()
        self.start_watcher_service()

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Starts watching the game files (reload_service).
        3. Yields the status again with completed=True, and the error text in
           message when starting failed.
        Never raises. It is critical: when it fails the system check stops and
        the dashboard does not open.
        """
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

    async def watch_status_file_and_publish_event(self) -> None:
        """Publishes a StatusEvent every time the game rewrites Status.json
        (ship flags, fuel, pips). Runs until exit_signal is set."""
        await self.__watch_side_file_and_publish_event("Status.json", StatusEvent)

    async def watch_market_file_and_publish_event(self) -> None:
        """Publishes a MarketEvent every time the game rewrites Market.json
        (commodities of the station market). Runs until exit_signal is set."""
        await self.__watch_side_file_and_publish_event("Market.json", MarketEvent)

    async def __watch_side_file_and_publish_event(self, file_name, event_model) -> None:
        """Checks the file next to the journal once a second until exit_signal
        is set.

        - File missing -> logs a warning and checks again in 1 s.
        - Modified time changed -> reads the whole file, parses it as
          event_model and publishes it on the event bus. The first check
          always counts as changed.
        - Empty file -> nothing is published.
        A file that does not parse is logged and skipped.
        """
        file_path = os.path.join(self.journal_path, file_name)
        last_modified_time = None
        while True:
            if self.exit_signal:
                break

            if not os.path.isfile(file_path):
                logger.warning(
                    "%s not found at '%s'. Waiting for it to appear...",
                    file_name,
                    file_path,
                )
                await asyncio.sleep(1)
                continue

            current_modified_time = os.path.getmtime(file_path)
            if current_modified_time != last_modified_time:
                last_modified_time = current_modified_time
                with open(file_path, "r") as f:
                    line = f.read()
                    if line:
                        try:
                            event = event_model.model_validate_json(line)
                            await self.event_bus.publish(event)
                        except ValidationError:
                            logger.error(
                                "Error during validation for %s event: %s",
                                file_name,
                                line,
                            )

            await asyncio.sleep(1)
