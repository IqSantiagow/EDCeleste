import unittest
from datetime import datetime
from unittest.mock import patch, mock_open, Mock

from services.journal_watcher_service import JournalWatcherService
from services.models.game_events import UnknownCheckedEvent
from services.models.settings_model import LLMModel, PathModel, SettingsModel, TTSModel

JOURNAL_PATH = "C:/journals"


def _make_settings(journal_path: str) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path=journal_path, keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="sp", user_prompt=""),
    )


class JournalWatcherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        glob_patcher = patch("services.journal_watcher_service.glob.glob")
        getmtime_patcher = patch("services.journal_watcher_service.os.path.getmtime")

        self.mock_glob = glob_patcher.start()
        self.mock_getmtime = getmtime_patcher.start()

        self.addCleanup(glob_patcher.stop)
        self.addCleanup(getmtime_patcher.stop)

        self.mock_glob.return_value = [f"{JOURNAL_PATH}/Journal.log"]
        self.mock_getmtime.return_value = 100

    def _make_event(self, event_name="SomeEvent"):
        return UnknownCheckedEvent(event=event_name, timestamp=datetime.now())

    def _make_watcher(self):
        return JournalWatcherService(
            journal_path=JOURNAL_PATH, event_bus=Mock(), settings_handler=Mock()
        )

    def test_get_latest_journal_filepath(self):
        self.mock_glob.return_value = [
            f"{JOURNAL_PATH}/Journal.2024-01-01.log",
            f"{JOURNAL_PATH}/Journal.2024-01-02.log",
        ]

        self.mock_getmtime.side_effect = [100, 200]

        watcher = self._make_watcher()

        result = watcher._JournalWatcherService__get_latest_journal_filepath()  # type: ignore

        self.assertEqual(result, f"{JOURNAL_PATH}/Journal.2024-01-02.log")

    def test_no_journal_files_raises_error(self):
        self.mock_glob.return_value = []

        watcher = self._make_watcher()

        with self.assertRaises(FileNotFoundError):
            watcher._JournalWatcherService__get_latest_journal_filepath()  # type: ignore

    async def test_follow_journal_lines(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            mock_open_file.readline.side_effect = [
                event1.model_dump_json(),
                event2.model_dump_json(),
            ]

            watcher = self._make_watcher()

            gen = watcher._JournalWatcherService__generate_journal_events()  # type: ignore

            self.assertEqual(await gen.__anext__(), event1)
            self.assertEqual(await gen.__anext__(), event2)

    async def test_should_stop_emitting_events_on_stop_signal(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            mock_open_file.readline.side_effect = [
                event1.model_dump_json(),
                event2.model_dump_json(),
            ]

            watcher = self._make_watcher()

            gen = watcher._JournalWatcherService__generate_journal_events()  # type: ignore

            self.assertEqual(await gen.__anext__(), event1)

            watcher.stop_watcher_service()

            with self.assertRaises(StopAsyncIteration):
                await gen.__anext__()

    def test_should_return_true_when_watcher_is_running(self):
        watcher = self._make_watcher()

        self.assertTrue(watcher.get_journal_healthcheck())

    def test_should_return_false_when_watcher_is_stopped(self):
        watcher = self._make_watcher()

        watcher.stop_watcher_service()

        self.assertFalse(watcher.get_journal_healthcheck())

    async def test_should_start_emitting_events(self):
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

            gen = watcher._JournalWatcherService__generate_journal_events()  # type: ignore

            self.assertEqual(await gen.__anext__(), event1)

            watcher.stop_watcher_service()

            with self.assertRaises(StopAsyncIteration):
                await gen.__anext__()

            watcher.exit_signal = False
            gen = watcher._JournalWatcherService__generate_journal_events()  # type: ignore

            self.assertEqual(await gen.__anext__(), event2)

    def test_validate_settings_reports_issue_when_journal_path_missing(self):
        watcher = self._make_watcher()
        new_settings = _make_settings(journal_path="")

        issues = watcher.validate_settings(new_settings)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].field, "journal_path")

    def test_validate_settings_returns_no_issues_when_journal_path_present(self):
        watcher = self._make_watcher()
        new_settings = _make_settings(journal_path=JOURNAL_PATH)

        issues = watcher.validate_settings(new_settings)

        self.assertEqual(issues, [])

    async def test_reload_service_restarts_watcher_with_settings_from_handler(self):
        settings_handler = Mock()
        new_settings = _make_settings(journal_path="C:/new-journals")
        settings_handler.get_settings.return_value = new_settings
        watcher = JournalWatcherService(
            journal_path=JOURNAL_PATH,
            event_bus=Mock(),
            settings_handler=settings_handler,
        )
        watcher.stop_watcher_service = Mock()
        watcher.start_watcher_service = Mock()

        watcher.reload_service()

        self.assertEqual(watcher.journal_path, "C:/new-journals")
        watcher.stop_watcher_service.assert_called_once()
        watcher.start_watcher_service.assert_called_once()


if __name__ == "__main__":
    unittest.main()
