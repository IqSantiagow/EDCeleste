import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch, mock_open, AsyncMock, Mock, call

from edceleste.services.journal_watcher_service import JournalWatcherService
from edceleste.services.models.game_events import UnknownCheckedEvent

JOURNAL_PATH = "C:/journals"


def _make_mock_event_bus() -> Mock:
    mock_event_bus = Mock()
    mock_event_bus.publish = AsyncMock()
    return mock_event_bus


class JournalWatcherEventBusTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        glob_patcher = patch("edceleste.services.journal_watcher_service.glob.glob")
        getmtime_patcher = patch(
            "edceleste.services.journal_watcher_service.os.path.getmtime"
        )

        self.mock_glob = glob_patcher.start()
        self.mock_getmtime = getmtime_patcher.start()

        self.addCleanup(glob_patcher.stop)
        self.addCleanup(getmtime_patcher.stop)

        self.mock_glob.return_value = [f"{JOURNAL_PATH}/Journal.log"]
        self.mock_getmtime.return_value = 100

    def _make_event(self, event_name="SomeEvent"):
        return UnknownCheckedEvent(event=event_name, timestamp=datetime.now())

    async def _run_watcher_task(self, watcher):
        # start_watcher_service() fires a background task and returns
        # immediately; awaiting it here lets the task run until it stops
        # itself (via stop_watcher_service(), which cancels the task).
        watcher.start_watcher_service()
        try:
            await watcher._journal_watcher_task
        except asyncio.CancelledError:
            pass

    async def test_follow_journal_lines(self):
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

            watcher = JournalWatcherService(
                journal_path=JOURNAL_PATH,
                event_bus=mock_event_bus,
                settings_handler=Mock(),
            )

            await self._run_watcher_task(watcher)

            mock_event_bus.publish.assert_has_calls(
                [call(event1), call(event2)], any_order=True
            )

    async def test_should_stop_emitting_events_on_stop_signal(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")

        mock_event_bus = _make_mock_event_bus()

        watcher = JournalWatcherService(
            journal_path=JOURNAL_PATH, event_bus=mock_event_bus, settings_handler=Mock()
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

            mock_event_bus.publish.assert_called_once_with(event1)

            with self.assertRaises(AssertionError):
                mock_event_bus.publish.assert_called_once_with(event2)

    async def test_should_start_emitting_events(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        event3 = self._make_event("SomeEvent3")

        mock_event_bus = _make_mock_event_bus()

        watcher = JournalWatcherService(
            journal_path=JOURNAL_PATH, event_bus=mock_event_bus, settings_handler=Mock()
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

            mock_event_bus.publish.assert_has_calls(
                [call(event1), call(event2)], any_order=True
            )

            with self.assertRaises(AssertionError):
                mock_event_bus.publish.assert_called_once_with(event3)

            await self._run_watcher_task(watcher)

            mock_event_bus.publish.assert_has_calls([call(event3)])


if __name__ == "__main__":
    unittest.main()
