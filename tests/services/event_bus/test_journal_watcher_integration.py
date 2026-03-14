import unittest
from datetime import datetime
from unittest.mock import patch, mock_open, Mock, call

from services.journal_watcher import JournalWatcherService
from services.models.game_events import UnknownCheckedEvent

JOURNAL_PATH = "C:/journals"


class JournalWatcherEventBusTest(unittest.TestCase):
    def setUp(self):
        glob_patcher = patch("services.journal_watcher.glob.glob")
        getmtime_patcher = patch("services.journal_watcher.os.path.getmtime")

        self.mock_glob = glob_patcher.start()
        self.mock_getmtime = getmtime_patcher.start()

        self.addCleanup(glob_patcher.stop)
        self.addCleanup(getmtime_patcher.stop)

        self.mock_glob.return_value = [f"{JOURNAL_PATH}/Journal.log"]
        self.mock_getmtime.return_value = 100

    def _make_event(self, event_name="SomeEvent"):
        return UnknownCheckedEvent(event=event_name, timestamp=datetime.now())

    def test_follow_journal_lines(self):
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

            mock_event_bus = Mock()

            watcher = JournalWatcherService(
                journal_path=JOURNAL_PATH, event_bus=mock_event_bus
            )

            watcher.start_watcher_service()

            mock_event_bus.publish.assert_has_calls(
                [call(event1), call(event2)], any_order=True
            )

    def test_should_stop_emitting_events_on_stop_signal(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")

        mock_event_bus = Mock()

        watcher = JournalWatcherService(
            journal_path=JOURNAL_PATH, event_bus=mock_event_bus
        )

        def readline_side_effect():
            yield event1.model_dump_json()
            watcher.stop_watcher_service()
            yield ""
            yield event2

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            mock_open_file.readline.side_effect = readline_side_effect()

            watcher.start_watcher_service()

            mock_event_bus.publish.assert_called_once_with(event1)

            with self.assertRaises(AssertionError):
                mock_event_bus.publish.assert_called_once_with(event2)

    def test_should_start_emitting_events(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        event3 = self._make_event("SomeEvent3")

        mock_event_bus = Mock()

        watcher = JournalWatcherService(
            journal_path=JOURNAL_PATH, event_bus=mock_event_bus
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

            watcher.start_watcher_service()

            mock_event_bus.publish.assert_has_calls(
                [call(event1), call(event2)], any_order=True
            )

            with self.assertRaises(AssertionError):
                mock_event_bus.publish.assert_called_once_with(event3)

            watcher.start_watcher_service()

            mock_event_bus.publish.assert_has_calls([call(event3)])


if __name__ == "__main__":
    unittest.main()
