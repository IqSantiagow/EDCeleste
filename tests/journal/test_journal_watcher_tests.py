import unittest
from datetime import datetime
from unittest.mock import patch, mock_open

from pydantic import TypeAdapter

from services.journal_watcher import JournalWatcherService
from services.models.game_events import UnknownCheckedEvent
from services.models.journal_event import JournalEvent


class JournalWatcherTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = TypeAdapter(JournalEvent)

    @patch("services.journal_watcher.glob.glob")
    @patch("services.journal_watcher.os.path.getmtime")
    def test_get_latest_journal_filepath(self, mock_getmtime, mock_glob):
        mock_glob.return_value = [
            "C:/journals/Journal.2024-01-01.log",
            "C:/journals/Journal.2024-01-02.log",
        ]

        mock_getmtime.side_effect = [
            100,
            200,
        ]  # getCtime is called for every file that is why it has to be iterable, not array, and we use side_effect

        watcher = JournalWatcherService("C:/journals")

        result = watcher._JournalWatcherService__get_latest_journal_filepath()

        self.assertEqual(result, "C:/journals/Journal.2024-01-02.log")

    @patch("services.journal_watcher.glob.glob")
    def test_no_journal_files_raises_error(self, mock_glob):
        mock_glob.return_value = []

        watcher = JournalWatcherService("C:/journals")

        with self.assertRaises(FileNotFoundError):
            watcher._JournalWatcherService__get_latest_journal_filepath()

    @patch("services.journal_watcher.glob.glob")
    @patch("services.journal_watcher.os.path.getmtime")
    def test_follow_journal_lines(self, mock_getmtime, mock_glob):
        mock_glob.return_value = ["C:/journals/Journal.log"]
        mock_getmtime.return_value = 100

        event1 = UnknownCheckedEvent(event="SomeEvent1", timestamp=datetime.now())
        event2 = UnknownCheckedEvent(event="SomeEvent2", timestamp=datetime.now())

        with patch("builtins.open", mock_open()) as m:
            # By creating mock object we call open() function
            mock_open_file = m()

            mock_open_file.readline.side_effect = [
                event1.model_dump_json(),
                event2.model_dump_json(),
            ]
            watcher = JournalWatcherService("C:/journals")

            gen = watcher.emit_journal_events()

            self.assertEqual(next(gen), event1)
            self.assertEqual(next(gen), event2)

    @patch("services.journal_watcher.glob.glob")
    @patch("services.journal_watcher.os.path.getmtime")
    def test_should_stop_emitting_events_on_stop_signal(self, mock_getmtime, mock_glob):
        mock_glob.return_value = ["C:/journals/Journal.log"]
        mock_getmtime.return_value = 100

        event1 = UnknownCheckedEvent(event="SomeEvent1", timestamp=datetime.now())
        event2 = UnknownCheckedEvent(event="SomeEvent2", timestamp=datetime.now())

        with patch("builtins.open", mock_open()) as m:
            # By creating mock object we call open() function
            mock_open_file = m()

            mock_open_file.readline.side_effect = [
                event1.model_dump_json(),
                event2.model_dump_json(),
            ]
            watcher = JournalWatcherService("C:/journals")

            gen = watcher.emit_journal_events()

            self.assertEqual(next(gen), event1)

            watcher.stop_watcher_service()

            with self.assertRaises(StopIteration):
                next(gen)

    @patch("services.journal_watcher.glob.glob")
    @patch("services.journal_watcher.os.path.getmtime")
    def test_should_start_emitting_events(self, mock_getmtime, mock_glob):
        mock_glob.return_value = ["C:/journals/Journal.log"]
        mock_getmtime.return_value = 100

        event1 = UnknownCheckedEvent(event="SomeEvent1", timestamp=datetime.now())
        event2 = UnknownCheckedEvent(event="SomeEvent2", timestamp=datetime.now())
        event3 = UnknownCheckedEvent(event="SomeEvent3", timestamp=datetime.now())

        with patch("builtins.open", mock_open()) as m:
            # By creating mock object we call open() function
            mock_open_file = m()

            mock_open_file.readline.side_effect = [
                event1.model_dump_json(),
                event2.model_dump_json(),
                event3.model_dump_json(),
            ]
            watcher = JournalWatcherService("C:/journals")

            gen = watcher.emit_journal_events()

            self.assertEqual(next(gen), event1)

            watcher.stop_watcher_service()

            with self.assertRaises(StopIteration):
                next(gen)

            gen = watcher.emit_journal_events()

            self.assertEqual(next(gen), event2)

if __name__ == "__main__":
    unittest.main()
