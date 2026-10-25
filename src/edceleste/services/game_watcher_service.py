import asyncio
import glob
import logging
import os
from typing import AsyncGenerator, TextIO

from pydantic import TypeAdapter, ValidationError

from edceleste.services.event_bus import EventBus
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.game_events import GameEvent, MarketEvent, StatusEvent
from edceleste.services.models.journal_event import JournalEvent
from edceleste.services.models.startup_loading_finished_event import (
    StartupLoadingFinishedEvent,
)
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
        """Starts one asyncio task on the running loop, so it needs a running
        loop. The task publishes game events on the event bus in two phases
        (see __load_game_state_then_follow_the_game_files):
        1. loading: everything the game had already written, silently,
        2. live: new lines of the newest Journal*.log file, Status.json and
           Market.json. The Status.json and Market.json watchers are two more
           tasks, which the first task starts when the loading is done.
        Sets exit_signal back to False, so the loops can run again after a
        stop. Returns at once, it does not wait for the task.
        Raises FileNotFoundError, before any task starts, when journal_path has
        no journal file. The journal file is picked only here, a new journal
        file written later by the game is not followed.
        Calling it twice without stop_watcher_service in between starts a
        second set of tasks, then every event is published twice.
        reload_service always stops first.
        """
        latest_journal_file_path = self.__get_latest_journal_filepath()

        self.exit_signal = False
        self._game_watcher_tasks.append(
            asyncio.create_task(
                self.__load_game_state_then_follow_the_game_files(
                    latest_journal_file_path
                )
            )
        )

    def stop_watcher_service(self) -> None:
        """Sets exit_signal, so the watch loops end, and cancels all watcher
        tasks. Safe to call when nothing is running."""
        self.exit_signal = True
        if self._game_watcher_tasks:
            for task in self._game_watcher_tasks:
                task.cancel()
            self._game_watcher_tasks.clear()

    async def __load_game_state_then_follow_the_game_files(
        self, journal_file_path: str
    ) -> None:
        """The whole life of the watcher, in this order:

        1. Loading: reads the journal from its first line to its end, then
           Status.json and Market.json once. Every event gets
           is_startup_loading=True, so it only builds the game state: no
           reaction, no LLM request.
        2. Publishes StartupLoadingFinishedEvent.
        3. Live: starts the Status.json and Market.json watchers (they skip
           the file version already loaded) and follows new journal lines on
           the same open file, from the place where the loading stopped, so no
           line written in between is lost.
        Runs until exit_signal is set or the task is cancelled. Stopping the
        watcher cancels this task, so a loading that is stopped halfway does
        not publish StartupLoadingFinishedEvent. The journal file is closed
        when the method ends. An OSError when the journal file cannot be
        opened ends the task with that error, nothing is published.
        """
        with open(
            journal_file_path, "r", encoding="utf-8", errors="replace"
        ) as journal_file:
            await self.__publish_lines_already_in_journal(journal_file)
            status_modified_time = await self.__publish_side_file_already_on_disk(
                "Status.json", StatusEvent
            )
            market_modified_time = await self.__publish_side_file_already_on_disk(
                "Market.json", MarketEvent
            )
            await self.event_bus.publish(StartupLoadingFinishedEvent())

            self._game_watcher_tasks.append(
                asyncio.create_task(
                    self.watch_status_file_and_publish_event(status_modified_time)
                )
            )
            self._game_watcher_tasks.append(
                asyncio.create_task(
                    self.watch_market_file_and_publish_event(market_modified_time)
                )
            )
            await self.__follow_open_journal_file_and_publish_new_lines(journal_file)

    async def __publish_lines_already_in_journal(self, journal_file: TextIO) -> None:
        """Reads the open journal file from its current place to its end (the
        caller has just opened it, so that is the first line) and publishes
        every line as an event with is_startup_loading=True. Stops earlier when
        exit_signal is set. Returns nothing.

        The file position stays at the end of what was read. The live follower
        (__follow_open_journal_file_and_publish_new_lines) continues from there.

        After every line it gives the event loop a turn, because a long
        journal has thousands of lines and the UI must stay alive meanwhile.
        A line that does not parse is logged and skipped. That includes a last
        line the game has not finished writing, it is lost."""
        while not self.exit_signal:
            line = journal_file.readline()
            if not line:
                return
            await self.__publish_journal_line(line, is_startup_loading=True)
            await asyncio.sleep(0)

    async def __follow_open_journal_file_and_publish_new_lines(
        self, journal_file: TextIO
    ) -> None:
        """Follows the open journal file like "tail -f" until exit_signal is
        set.

        1. Starts at the current place of the file, so the lines read by the
           loading are not published again.
        2. Checks for a new line every 0.1 s.
        3. Parses every new line as a JournalEvent (unknown events become
           UnknownCheckedEvent) and publishes it on the event bus as a live
           event.
        A line that does not parse is logged and skipped. That includes a line
        the game is writing right now and has not finished, it is lost. An
        error of the read itself is not caught: it ends this task.
        """
        while True:
            if self.exit_signal:
                break
            line = journal_file.readline()
            if not line:
                await asyncio.sleep(0.1)
                continue
            await self.__publish_journal_line(line, is_startup_loading=False)

    async def __publish_journal_line(self, line: str, is_startup_loading: bool) -> None:
        """Parses one journal line as a JournalEvent (an event name we do not
        know becomes UnknownCheckedEvent), sets is_startup_loading on it and
        publishes it on the event bus. Waits until every subscriber has
        handled it.

        A line that does not parse (bad JSON, fields that fail the model, an
        empty line) is logged and skipped, nothing is published and nothing is
        raised. Errors of the subscribers do not come back, the event bus
        swallows them."""
        try:
            event = self.adapter.validate_json(line.strip())
            event.is_startup_loading = is_startup_loading
            await self.event_bus.publish(event)
        except ValidationError:
            logger.error("Error during validation for event: %s", line)

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
        new path has no journal file, then nothing is watched (the old watcher
        is already stopped).

        The new task loads the journal from its first line again, silently
        (see start_watcher_service), and publishes a second
        StartupLoadingFinishedEvent. Nothing clears the projections first.
        They overwrite their values, so the same events give the same game
        state."""
        new_settings = self.__settings_service.get_settings()
        self.journal_path = new_settings.paths.journal_path
        self.stop_watcher_service()
        self.start_watcher_service()

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Starts watching the game files (reload_service). The loading of the
           game state runs on in the background, the check does not wait for it.
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

    async def watch_status_file_and_publish_event(
        self, last_modified_time: float | None = None
    ) -> None:
        """Publishes a StatusEvent every time the game rewrites Status.json
        (ship flags, fuel, pips). Runs until exit_signal is set. Returns
        nothing. It is public, but the watcher task starts it, so calling it
        from outside adds a second watcher of the same file.

        last_modified_time is the version of the file that is already known
        (loaded at startup), as os.path.getmtime gives it: seconds as a
        float. That version is not published again. None means every version
        counts as new."""
        await self.__watch_side_file_and_publish_event(
            "Status.json", StatusEvent, last_modified_time
        )

    async def watch_market_file_and_publish_event(
        self, last_modified_time: float | None = None
    ) -> None:
        """Publishes a MarketEvent every time the game rewrites Market.json
        (commodities of the station market). Runs until exit_signal is set.
        Returns nothing. The game writes Market.json only after the pilot
        opens a market, until then it logs a warning every second. It is
        public, but the watcher task starts it, so calling it from outside
        adds a second watcher of the same file.

        last_modified_time is the version of the file that is already known
        (loaded at startup), as os.path.getmtime gives it: seconds as a
        float. That version is not published again. None means every version
        counts as new."""
        await self.__watch_side_file_and_publish_event(
            "Market.json", MarketEvent, last_modified_time
        )

    def __read_side_file_event(
        self, file_name: str, event_model: type[GameEvent]
    ) -> GameEvent | None:
        """Reads the whole file file_name in the journal folder
        (self.journal_path) and parses it as event_model. Publishes nothing.
        Returns the event. Returns None for an empty file, and for a file that
        does not parse (that one is logged, for example when the game is
        rewriting it right now). Raises OSError when the file cannot be
        opened."""
        file_path = os.path.join(self.journal_path, file_name)
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        if not text:
            return None
        try:
            return event_model.model_validate_json(text)
        except ValidationError:
            logger.error(
                "Error during validation for %s event: %s",
                file_name,
                text,
            )
            return None

    async def __publish_side_file_already_on_disk(
        self, file_name: str, event_model: type[GameEvent]
    ) -> float | None:
        """Loads one side file (Status.json or Market.json) at startup. When
        the file is there, publishes its content once as an event with
        is_startup_loading=True and waits until the subscribers have handled it.

        Returns the modified time of the file that was read, so the live
        watcher does not publish the same version again. That also holds when
        the file is empty or does not parse: nothing is published, but the time
        is returned, and the live watcher waits for the next rewrite.
        Returns None when the file does not exist yet (the game writes
        Market.json only after the pilot opens a market), then a file that
        appears later is live. Also returns None, and logs the error, when the
        file cannot be read (OSError, for example while the game holds it): the
        live watcher then reads it as a live event, and the journal keeps being
        followed."""
        file_path = os.path.join(self.journal_path, file_name)
        if not os.path.isfile(file_path):
            return None

        try:
            modified_time = os.path.getmtime(file_path)
            event = self.__read_side_file_event(file_name, event_model)
        except OSError:
            logger.exception("Cannot read %s at startup: %s", file_name, file_path)
            return None
        if event is not None:
            event.is_startup_loading = True
            await self.event_bus.publish(event)
        return modified_time

    async def __watch_side_file_and_publish_event(
        self,
        file_name: str,
        event_model: type[GameEvent],
        last_modified_time: float | None,
    ) -> None:
        """Checks the file next to the journal once a second until exit_signal
        is set.

        - File missing -> logs a warning and checks again in 1 s.
        - Modified time differs from last_modified_time -> reads the whole
          file, parses it as event_model and publishes it on the event bus as
          a live event.
        - Empty file -> nothing is published.
        A file that does not parse is logged and skipped. The modified time is
        remembered before the file is read, so an empty or broken version is
        logged once, not every second, and the next rewrite is tried again.
        An OSError while reading is not caught: it ends this watcher task and
        the other tasks go on.
        """
        file_path = os.path.join(self.journal_path, file_name)
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
                event = self.__read_side_file_event(file_name, event_model)
                if event is not None:
                    await self.event_bus.publish(event)

            await asyncio.sleep(1)
