import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch, mock_open, AsyncMock, Mock

from edceleste.services.game_watcher_service import GameWatcherService
from edceleste.services.models.game_events import UnknownCheckedEvent
from edceleste.services.models.startup_loading_finished_event import (
    StartupLoadingFinishedEvent,
)

JOURNAL_PATH = "C:/journals"


def _make_mock_event_bus() -> Mock:
    mock_event_bus = Mock()
    mock_event_bus.publish = AsyncMock()
    return mock_event_bus


class JournalWatcherEventBusTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        glob_patcher = patch("edceleste.services.game_watcher_service.glob.glob")
        getmtime_patcher = patch(
            "edceleste.services.game_watcher_service.os.path.getmtime"
        )
        # start_watcher_service() also spawns a watcher task per side file
        # (SIDE_FILES). This test file only covers the
        # journal-line event bus integration, so those tasks are replaced with
        # harmless no-ops - otherwise they would race the journal task for the
        # same mocked builtins.open()/readline() on any machine where those
        # files happen to exist under JOURNAL_PATH.
        watch_side_file_patcher = patch.object(
            GameWatcherService,
            "watch_side_file_and_publish_event",
            new=AsyncMock(),
        )

        self.mock_glob = glob_patcher.start()
        self.mock_getmtime = getmtime_patcher.start()
        watch_side_file_patcher.start()

        self.addCleanup(glob_patcher.stop)
        self.addCleanup(getmtime_patcher.stop)
        self.addCleanup(watch_side_file_patcher.stop)

        self.mock_glob.return_value = [f"{JOURNAL_PATH}/Journal.log"]
        self.mock_getmtime.return_value = 100

    def _make_event(self, event_name="SomeEvent"):
        return UnknownCheckedEvent(event=event_name, timestamp=datetime.now())

    def _published(self, mock_event_bus) -> list:
        """What the watcher put on the bus: (event name, is it a startup
        loading event) for game events, the class name for the rest."""
        published = []
        for published_call in mock_event_bus.publish.await_args_list:
            event = published_call.args[0]
            if isinstance(event, StartupLoadingFinishedEvent):
                published.append("StartupLoadingFinishedEvent")
            else:
                published.append((event.event, event.is_startup_loading))
        return published

    async def _run_watcher_task(self, watcher):
        # start_watcher_service() fires the journal task and returns
        # immediately; awaiting it here lets it run until it stops itself (via
        # stop_watcher_service(), which cancels every task it started,
        # journal task included). The journal task is the last one in the
        # list right after the start. After a stop the list can still hold the
        # side file tasks of the previous run, so the first entry is not it.
        watcher.start_watcher_service()
        journal_task = watcher._game_watcher_tasks[-1]
        try:
            await journal_task
        except asyncio.CancelledError:
            pass

    async def test_lines_in_the_file_at_start_are_loaded_then_loading_is_finished(
        self,
    ):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")

        def readline_side_effect():
            yield event1.model_dump_json()
            yield event2.model_dump_json()
            watcher.stop_watcher_service()
            yield ""

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            mock_open_file.readline.side_effect = readline_side_effect()

            mock_event_bus = _make_mock_event_bus()

            watcher = GameWatcherService(
                journal_path=JOURNAL_PATH,
                event_bus=mock_event_bus,
                settings_service=Mock(),
            )

            await self._run_watcher_task(watcher)

            self.assertEqual(
                self._published(mock_event_bus),
                [
                    ("SomeEvent1", True),
                    ("SomeEvent2", True),
                    "StartupLoadingFinishedEvent",
                ],
            )

    async def test_should_stop_emitting_events_on_stop_signal(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")

        mock_event_bus = _make_mock_event_bus()

        watcher = GameWatcherService(
            journal_path=JOURNAL_PATH, event_bus=mock_event_bus, settings_service=Mock()
        )

        def readline_side_effect():
            yield event1.model_dump_json()
            watcher.stop_watcher_service()
            yield ""
            yield event2

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            mock_open_file.readline.side_effect = readline_side_effect()

            await self._run_watcher_task(watcher)

            # event2 is behind the stop signal, so it is never read.
            self.assertEqual(
                self._published(mock_event_bus),
                [("SomeEvent1", True), "StartupLoadingFinishedEvent"],
            )

    async def test_should_start_emitting_events(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        event3 = self._make_event("SomeEvent3")

        mock_event_bus = _make_mock_event_bus()

        watcher = GameWatcherService(
            journal_path=JOURNAL_PATH, event_bus=mock_event_bus, settings_service=Mock()
        )

        def readline_side_effect():
            yield event1.model_dump_json()
            yield event2.model_dump_json()
            watcher.stop_watcher_service()
            yield ""
            yield event3.model_dump_json()
            watcher.stop_watcher_service()
            yield ""

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            mock_open_file.readline.side_effect = readline_side_effect()

            await self._run_watcher_task(watcher)

            self.assertEqual(
                self._published(mock_event_bus),
                [
                    ("SomeEvent1", True),
                    ("SomeEvent2", True),
                    "StartupLoadingFinishedEvent",
                ],
            )

            await self._run_watcher_task(watcher)

            self.assertEqual(
                self._published(mock_event_bus)[3:],
                [("SomeEvent3", True), "StartupLoadingFinishedEvent"],
            )


if __name__ == "__main__":
    unittest.main()
