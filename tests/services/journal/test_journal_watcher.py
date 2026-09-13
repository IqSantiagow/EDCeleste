import unittest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, mock_open, patch

from edceleste.services.game_watcher_service import GameWatcherService
from edceleste.services.models.game_events import StatusEvent, UnknownCheckedEvent
from edceleste.services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)

JOURNAL_PATH = "C:/journals"


def _make_settings(journal_path: str) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path=journal_path, keybindings_path="C:/k"),
        tts=TTSModel(volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="sp", user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


class JournalWatcherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        glob_patcher = patch("edceleste.services.game_watcher_service.glob.glob")
        getmtime_patcher = patch(
            "edceleste.services.game_watcher_service.os.path.getmtime"
        )
        isdir_patcher = patch("edceleste.services.game_watcher_service.os.path.isdir")

        self.mock_glob = glob_patcher.start()
        self.mock_getmtime = getmtime_patcher.start()
        self.mock_isdir = isdir_patcher.start()

        self.addCleanup(glob_patcher.stop)
        self.addCleanup(getmtime_patcher.stop)
        self.addCleanup(isdir_patcher.stop)

        self.mock_glob.return_value = [f"{JOURNAL_PATH}/Journal.log"]
        self.mock_getmtime.return_value = 100
        self.mock_isdir.return_value = True

    def _make_event(self, event_name="SomeEvent"):
        return UnknownCheckedEvent(event=event_name, timestamp=datetime.now())

    def _make_watcher(self):
        self.mock_event_bus = AsyncMock()
        return GameWatcherService(
            journal_path=JOURNAL_PATH,
            event_bus=self.mock_event_bus,
            settings_handler=Mock(),
        )

    def test_get_latest_journal_filepath(self):
        self.mock_glob.return_value = [
            f"{JOURNAL_PATH}/Journal.2024-01-01.log",
            f"{JOURNAL_PATH}/Journal.2024-01-02.log",
        ]

        self.mock_getmtime.side_effect = [100, 200]

        watcher = self._make_watcher()

        result = watcher._GameWatcherService__get_latest_journal_filepath()  # type: ignore

        self.assertEqual(result, f"{JOURNAL_PATH}/Journal.2024-01-02.log")

    def test_no_journal_files_raises_error(self):
        self.mock_glob.return_value = []

        watcher = self._make_watcher()

        with self.assertRaises(FileNotFoundError):
            watcher._GameWatcherService__get_latest_journal_filepath()  # type: ignore

    async def test_follow_journal_lines(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            watcher = self._make_watcher()

            def readline_side_effect():
                yield event1.model_dump_json()
                yield event2.model_dump_json()
                watcher.stop_watcher_service()
                yield ""

            mock_open_file.readline.side_effect = readline_side_effect()

            await watcher._GameWatcherService__generate_journal_events()  # type: ignore

            self.assertEqual(
                self.mock_event_bus.publish.await_args_list,
                [((event1,),), ((event2,),)],
            )

    async def test_should_stop_emitting_events_on_stop_signal(self):
        event1 = self._make_event("SomeEvent1")

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            watcher = self._make_watcher()

            def readline_side_effect():
                yield event1.model_dump_json()
                watcher.stop_watcher_service()
                yield ""

            mock_open_file.readline.side_effect = readline_side_effect()

            await watcher._GameWatcherService__generate_journal_events()  # type: ignore

            self.mock_event_bus.publish.assert_awaited_once_with(event1)

    async def test_should_start_emitting_events(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        event3 = self._make_event("SomeEvent3")

        with patch("builtins.open", mock_open()) as m:
            mock_open_file = m()

            watcher = self._make_watcher()

            def readline_side_effect():
                yield event1.model_dump_json()
                yield event2.model_dump_json()
                watcher.stop_watcher_service()
                yield ""
                yield event3.model_dump_json()
                watcher.stop_watcher_service()
                yield ""

            mock_open_file.readline.side_effect = readline_side_effect()

            await watcher._GameWatcherService__generate_journal_events()  # type: ignore

            self.assertEqual(
                self.mock_event_bus.publish.await_args_list,
                [((event1,),), ((event2,),)],
            )

            watcher.exit_signal = False
            await watcher._GameWatcherService__generate_journal_events()  # type: ignore

            self.assertEqual(
                self.mock_event_bus.publish.await_args_list,
                [((event1,),), ((event2,),), ((event3,),)],
            )

    def test_validate_settings_reports_issue_when_journal_path_missing(self):
        watcher = self._make_watcher()
        new_settings = _make_settings(journal_path="")

        issue = watcher.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.field, "journal_path")

    def test_validate_settings_returns_no_issues_when_journal_path_present(self):
        watcher = self._make_watcher()
        new_settings = _make_settings(journal_path=JOURNAL_PATH)

        issue = watcher.validate_settings(new_settings)

        self.assertIsNone(issue)

    async def test_reload_service_restarts_watcher_with_settings_from_handler(self):
        settings_handler = Mock()
        new_settings = _make_settings(journal_path="C:/new-journals")
        settings_handler.get_settings.return_value = new_settings
        watcher = GameWatcherService(
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

    # --- watch_status_file_and_generate_event ---

    async def test_watch_status_file_waits_until_status_file_appears(self):
        status_event = StatusEvent(
            event="Status", timestamp=datetime.now(), Flags=1, Flags2=0
        )
        watcher = self._make_watcher()

        sleep_calls = []

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 2:
                watcher.stop_watcher_service()

        with (
            patch(
                "edceleste.services.game_watcher_service.os.path.isfile",
                side_effect=[False, True],
            ),
            patch("builtins.open", mock_open(read_data=status_event.model_dump_json())),
            patch(
                "edceleste.services.game_watcher_service.asyncio.sleep",
                new=AsyncMock(side_effect=fake_sleep),
            ),
        ):
            await watcher.watch_status_file_and_generate_event()

        # First pass finds no file and only waits; the event is only
        # published once Status.json actually shows up on disk.
        self.mock_event_bus.publish.assert_awaited_once_with(status_event)

    async def test_watch_status_file_skips_invalid_status_json(self):
        watcher = self._make_watcher()

        async def fake_sleep(_seconds):
            watcher.stop_watcher_service()

        with (
            patch(
                "edceleste.services.game_watcher_service.os.path.isfile",
                return_value=True,
            ),
            patch("builtins.open", mock_open(read_data="not valid json")),
            patch(
                "edceleste.services.game_watcher_service.asyncio.sleep",
                new=AsyncMock(side_effect=fake_sleep),
            ),
        ):
            await watcher.watch_status_file_and_generate_event()

        self.mock_event_bus.publish.assert_not_awaited()

    async def test_watch_status_file_only_republishes_on_change(self):
        status_event = StatusEvent(
            event="Status", timestamp=datetime.now(), Flags=1, Flags2=0
        )
        watcher = self._make_watcher()

        sleep_calls = []

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 2:
                watcher.stop_watcher_service()

        with (
            patch(
                "edceleste.services.game_watcher_service.os.path.isfile",
                return_value=True,
            ),
            # getmtime stays constant across both loop passes, so the second
            # pass must not re-read the file or re-publish the event.
            patch(
                "edceleste.services.game_watcher_service.os.path.getmtime",
                return_value=100,
            ),
            patch("builtins.open", mock_open(read_data=status_event.model_dump_json())),
            patch(
                "edceleste.services.game_watcher_service.asyncio.sleep",
                new=AsyncMock(side_effect=fake_sleep),
            ),
        ):
            await watcher.watch_status_file_and_generate_event()

        self.mock_event_bus.publish.assert_awaited_once_with(status_event)

    # --- cold_start ---

    async def test_cold_start_yields_pending_status_first(self):
        watcher = self._make_watcher()
        watcher.reload_service = Mock()

        # ColdStartStatus is mutated in place and re-yielded on completion, so
        # the pending status must be inspected right after this first yield -
        # collecting every yield into a list first would show the mutated,
        # already-completed object instead.
        first_status = await watcher.cold_start().__anext__()

        self.assertEqual(first_status.service, "journal_watcher")
        self.assertTrue(first_status.is_critical)
        self.assertFalse(first_status.completed)
        self.assertIsNone(first_status.message)

    async def test_cold_start_yields_completed_status_when_reload_service_succeeds(
        self,
    ):
        watcher = self._make_watcher()
        watcher.reload_service = Mock()

        statuses = [status async for status in watcher.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertIsNone(last_status.message)

    async def test_cold_start_yields_error_message_when_reload_service_fails(self):
        watcher = self._make_watcher()
        watcher.reload_service = Mock(side_effect=FileNotFoundError("no journal path"))

        statuses = [status async for status in watcher.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertEqual(last_status.message, "no journal path")


if __name__ == "__main__":
    unittest.main()
