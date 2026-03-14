import unittest
from datetime import datetime
from unittest.mock import patch, mock_open, Mock

from services.journal_watcher import JournalWatcherService
from services.models.game_events import UnknownCheckedEvent

JOURNAL_PATH = "C:/journals"


class JournalWatcherTest(unittest.TestCase):
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

    def _make_watcher(self):
        return JournalWatcherService(journal_path=JOURNAL_PATH, event_bus=Mock())

    def test_get_latest_journal_filepath(self):
        self.mock_glob.return_value = [
            f"{JOURNAL_PATH}/Journal.2024-01-01.log",
            f"{JOURNAL_PATH}/Journal.2024-01-02.log",
        ]

        self.mock_getmtime.side_effect = [100, 200]

        watcher = self._make_watcher()

        result = watcher._JournalWatcherService__get_latest_journal_filepath()

        self.assertEqual(result, f"{JOURNAL_PATH}/Journal.2024-01-02.log")

    def test_no_journal_files_raises_error(self):
        self.mock_glob.return_value = []

        watcher = self._make_watcher()

        with self.assertRaises(FileNotFoundError):
            watcher._JournalWatcherService__get_latest_journal_filepath()

    def test_follow_journal_lines(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            mock_open_file.readline.side_effect = [
                event1.model_dump_json(),
                event2.model_dump_json(),
            ]

            watcher = self._make_watcher()

            gen = watcher._JournalWatcherService__generate_journal_events()

            self.assertEqual(next(gen), event1)
            self.assertEqual(next(gen), event2)

    def test_should_stop_emitting_events_on_stop_signal(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            mock_open_file.readline.side_effect = [
                event1.model_dump_json(),
                event2.model_dump_json(),
            ]

            watcher = self._make_watcher()

            gen = watcher._JournalWatcherService__generate_journal_events()

            self.assertEqual(next(gen), event1)

            watcher.stop_watcher_service()

            with self.assertRaises(StopIteration):
                next(gen)

    def test_should_start_emitting_events(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        event3 = self._make_event("SomeEvent3")

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            mock_open_file.readline.side_effect = [
                event1.model_dump_json(),
                event2.model_dump_json(),
                event3.model_dump_json(),
            ]

            watcher = self._make_watcher()

            gen = watcher._JournalWatcherService__generate_journal_events()

            self.assertEqual(next(gen), event1)

            watcher.stop_watcher_service()

            with self.assertRaises(StopIteration):
                next(gen)

            watcher.exit_signal = False
            gen = watcher._JournalWatcherService__generate_journal_events()

            self.assertEqual(next(gen), event2)


if __name__ == "__main__":
    unittest.main()
