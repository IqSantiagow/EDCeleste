import asyncio
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, mock_open, patch

from edceleste.services.game_watcher_service import (
    SIDE_FILES,
    GameWatcherService,
    find_journal_files,
)
from edceleste.services.models.game_events import (
    MarketEvent,
    StatusEvent,
    UnknownCheckedEvent,
)
from edceleste.services.models.new_game_session_event import NewGameSessionEvent
from edceleste.services.models.startup_loading_finished_event import (
    StartupLoadingFinishedEvent,
)
from edceleste.services.models.service_status import ServiceState, ServiceStatus
from edceleste.services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)

RESOURCES = Path(__file__).parent.parent.parent / "resources"
JOURNAL_PATH = "C:/journals"
JOURNAL_FILE = f"{JOURNAL_PATH}/Journal.log"


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
            settings_service=Mock(),
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

    # --- following the journal live ---

    async def test_follow_journal_lines(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        watcher = self._make_watcher()

        def readline_side_effect():
            yield event1.model_dump_json()
            yield event2.model_dump_json()
            watcher.stop_watcher_service()
            yield ""

        journal_file = Mock()
        journal_file.readline.side_effect = readline_side_effect()

        await (
            watcher._GameWatcherService__follow_open_journal_file_and_publish_new_lines(
                journal_file
            )
        )  # type: ignore

        # The expected events are live ones (is_startup_loading False), the
        # comparison includes that flag.
        self.assertEqual(
            self.mock_event_bus.publish.await_args_list,
            [((event1,),), ((event2,),)],
        )
        for published_call in self.mock_event_bus.publish.await_args_list:
            self.assertFalse(published_call.args[0].is_startup_loading)

    async def test_should_stop_emitting_events_on_stop_signal(self):
        event1 = self._make_event("SomeEvent1")
        watcher = self._make_watcher()

        def readline_side_effect():
            yield event1.model_dump_json()
            watcher.stop_watcher_service()
            yield ""

        journal_file = Mock()
        journal_file.readline.side_effect = readline_side_effect()

        await (
            watcher._GameWatcherService__follow_open_journal_file_and_publish_new_lines(
                journal_file
            )
        )  # type: ignore

        self.mock_event_bus.publish.assert_awaited_once_with(event1)

    async def test_should_start_emitting_events(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        event3 = self._make_event("SomeEvent3")
        watcher = self._make_watcher()

        def readline_side_effect():
            yield event1.model_dump_json()
            yield event2.model_dump_json()
            watcher.stop_watcher_service()
            yield ""
            yield event3.model_dump_json()
            watcher.stop_watcher_service()
            yield ""

        journal_file = Mock()
        journal_file.readline.side_effect = readline_side_effect()

        await (
            watcher._GameWatcherService__follow_open_journal_file_and_publish_new_lines(
                journal_file
            )
        )  # type: ignore

        self.assertEqual(
            self.mock_event_bus.publish.await_args_list,
            [((event1,),), ((event2,),)],
        )

        watcher.exit_signal = False
        await (
            watcher._GameWatcherService__follow_open_journal_file_and_publish_new_lines(
                journal_file
            )
        )  # type: ignore

        self.assertEqual(
            self.mock_event_bus.publish.await_args_list,
            [((event1,),), ((event2,),), ((event3,),)],
        )

    # --- loading what the game wrote before the app started ---

    async def _load_side_file(self, watcher, file_name, event_model):
        """Calls the private loading of one side file and returns its result."""
        return await watcher._GameWatcherService__publish_side_file_already_on_disk(  # type: ignore
            file_name, event_model
        )

    async def test_lines_already_in_the_journal_are_published_as_startup_loading(
        self,
    ):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        watcher = self._make_watcher()
        journal_file = Mock()
        journal_file.readline.side_effect = [
            event1.model_dump_json(),
            event2.model_dump_json(),
            "",
        ]

        await watcher._GameWatcherService__publish_lines_already_in_journal(  # type: ignore
            journal_file
        )

        published_events = [
            published_call.args[0]
            for published_call in self.mock_event_bus.publish.await_args_list
        ]
        self.assertEqual(
            [event.event for event in published_events], ["SomeEvent1", "SomeEvent2"]
        )
        for published_event in published_events:
            self.assertTrue(published_event.is_startup_loading)

    async def test_loading_skips_a_line_that_does_not_parse_and_goes_on(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        watcher = self._make_watcher()
        journal_file = Mock()
        journal_file.readline.side_effect = [
            event1.model_dump_json(),
            "this is not a journal line",
            event2.model_dump_json(),
            "",
        ]

        await watcher._GameWatcherService__publish_lines_already_in_journal(  # type: ignore
            journal_file
        )

        published_names = [
            published_call.args[0].event
            for published_call in self.mock_event_bus.publish.await_args_list
        ]
        self.assertEqual(published_names, ["SomeEvent1", "SomeEvent2"])

    async def test_loading_stops_when_exit_signal_is_set(self):
        event1 = self._make_event("SomeEvent1")
        event2 = self._make_event("SomeEvent2")
        watcher = self._make_watcher()

        def readline_side_effect():
            yield event1.model_dump_json()
            watcher.exit_signal = True
            yield event2.model_dump_json()

        journal_file = Mock()
        journal_file.readline.side_effect = readline_side_effect()

        await watcher._GameWatcherService__publish_lines_already_in_journal(  # type: ignore
            journal_file
        )

        # event2 was already read when the signal came, but the loop checks
        # the signal before every read, so it is not read a third time.
        self.assertEqual(journal_file.readline.call_count, 2)

    async def test_side_file_already_on_disk_is_published_as_startup_loading(self):
        status_event = StatusEvent(
            event="Status", timestamp=datetime.now(), Flags=1, Flags2=0
        )
        watcher = self._make_watcher()

        with (
            patch(
                "edceleste.services.game_watcher_service.os.path.isfile",
                return_value=True,
            ),
            patch(
                "edceleste.services.game_watcher_service.os.path.getmtime",
                return_value=123.5,
            ),
            patch("builtins.open", mock_open(read_data=status_event.model_dump_json())),
        ):
            modified_time = await self._load_side_file(
                watcher, "Status.json", StatusEvent
            )

        self.assertEqual(modified_time, 123.5)
        published_event = self.mock_event_bus.publish.await_args.args[0]
        self.assertEqual(published_event.Flags, 1)
        self.assertTrue(published_event.is_startup_loading)

    async def test_side_file_missing_at_loading_publishes_nothing_and_has_no_time(
        self,
    ):
        watcher = self._make_watcher()

        with patch(
            "edceleste.services.game_watcher_service.os.path.isfile",
            return_value=False,
        ):
            modified_time = await self._load_side_file(
                watcher, "Market.json", MarketEvent
            )

        self.assertIsNone(modified_time)
        self.mock_event_bus.publish.assert_not_awaited()

    async def test_empty_or_broken_side_file_at_loading_publishes_nothing(self):
        for file_content in ["", "not valid json"]:
            with self.subTest(file_content=file_content):
                watcher = self._make_watcher()

                with (
                    patch(
                        "edceleste.services.game_watcher_service.os.path.isfile",
                        return_value=True,
                    ),
                    patch(
                        "edceleste.services.game_watcher_service.os.path.getmtime",
                        return_value=77,
                    ),
                    patch("builtins.open", mock_open(read_data=file_content)),
                ):
                    modified_time = await self._load_side_file(
                        watcher, "Status.json", StatusEvent
                    )

                # The file counts as seen, so the live watcher waits for the
                # next change instead of reading the same broken file again.
                self.assertEqual(modified_time, 77)
                self.mock_event_bus.publish.assert_not_awaited()

    async def test_side_file_that_cannot_be_read_at_loading_is_logged_not_raised(
        self,
    ):
        # An error here must not end the whole loading task: the journal still
        # has to be followed, and the live watcher tries the file again.
        watcher = self._make_watcher()

        with (
            patch(
                "edceleste.services.game_watcher_service.os.path.isfile",
                return_value=True,
            ),
            patch(
                "edceleste.services.game_watcher_service.os.path.getmtime",
                return_value=77,
            ),
            patch("builtins.open", side_effect=PermissionError("held by the game")),
            self.assertLogs(
                "edceleste.services.game_watcher_service", level="ERROR"
            ) as logs,
        ):
            modified_time = await self._load_side_file(
                watcher, "Status.json", StatusEvent
            )

        self.assertIsNone(modified_time)
        self.mock_event_bus.publish.assert_not_awaited()
        self.assertIn("Cannot read Status.json at startup", logs.output[0])

    async def test_live_side_watcher_skips_the_version_loaded_at_startup(self):
        status_event = StatusEvent(
            event="Status", timestamp=datetime.now(), Flags=1, Flags2=0
        )
        watcher = self._make_watcher()
        modified_times = [100, 100, 200]

        sleep_calls = []

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 3:
                watcher.stop_watcher_service()

        with (
            patch(
                "edceleste.services.game_watcher_service.os.path.isfile",
                return_value=True,
            ),
            patch(
                "edceleste.services.game_watcher_service.os.path.getmtime",
                side_effect=modified_times,
            ),
            patch("builtins.open", mock_open(read_data=status_event.model_dump_json())),
            patch(
                "edceleste.services.game_watcher_service.asyncio.sleep",
                new=AsyncMock(side_effect=fake_sleep),
            ),
        ):
            await watcher.watch_side_file_and_publish_event(
                "Status.json", StatusEvent, last_modified_time=100
            )

        # Passes 1 and 2 see the loaded version 100. Only the rewrite at
        # version 200 is published, and it is a live event.
        self.mock_event_bus.publish.assert_awaited_once_with(status_event)
        self.assertFalse(
            self.mock_event_bus.publish.await_args.args[0].is_startup_loading
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
        settings_service = Mock()
        new_settings = _make_settings(journal_path="C:/new-journals")
        settings_service.get_settings.return_value = new_settings
        watcher = GameWatcherService(
            journal_path=JOURNAL_PATH,
            event_bus=Mock(),
            settings_service=settings_service,
        )
        watcher.stop_watcher_service = Mock()
        watcher.start_watcher_service = Mock()

        watcher.reload_service()

        self.assertEqual(watcher.journal_path, "C:/new-journals")
        watcher.stop_watcher_service.assert_called_once()
        watcher.start_watcher_service.assert_called_once()

    # --- status for the app header ---

    async def _latest_status(self, watcher: GameWatcherService):
        """The status a new listener of stream_status() gets at once."""
        stream = watcher.stream_status()
        try:
            return await asyncio.wait_for(stream.__anext__(), timeout=1)
        finally:
            await stream.aclose()

    def _make_watcher_with_journal_path(self, journal_path: str) -> GameWatcherService:
        settings_service = Mock()
        settings_service.get_settings.return_value = _make_settings(journal_path)
        return GameWatcherService(
            journal_path=journal_path,
            event_bus=Mock(),
            settings_service=settings_service,
        )

    async def test_status_is_off_before_the_first_reload(self):
        watcher = self._make_watcher_with_journal_path(JOURNAL_PATH)

        status = await self._latest_status(watcher)

        self.assertEqual(status, ServiceStatus(ServiceState.OFF, "Not checked yet"))

    async def test_reload_service_sets_ok_status_when_the_watcher_starts(self):
        watcher = self._make_watcher_with_journal_path(JOURNAL_PATH)
        watcher.start_watcher_service = Mock()

        watcher.reload_service()

        status = await self._latest_status(watcher)
        self.assertEqual(
            status, ServiceStatus(ServiceState.OK, "Watching the journal folder")
        )

    async def test_reload_service_sets_error_status_and_raises_without_journal_file(
        self,
    ):
        self.mock_glob.return_value = []
        watcher = self._make_watcher_with_journal_path(JOURNAL_PATH)

        with self.assertRaises(FileNotFoundError):
            watcher.reload_service()

        status = await self._latest_status(watcher)
        self.assertEqual(status.state, ServiceState.ERROR)
        self.assertIn(JOURNAL_PATH, status.reason)

    # --- watch_side_file_and_publish_event with Status.json ---

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
            await watcher.watch_side_file_and_publish_event("Status.json", StatusEvent)

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
            await watcher.watch_side_file_and_publish_event("Status.json", StatusEvent)

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
            await watcher.watch_side_file_and_publish_event("Status.json", StatusEvent)

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

    # --- watch_side_file_and_publish_event with Market.json ---

    def _make_market_event(self):
        return MarketEvent(
            event="Market",
            timestamp=datetime.now(),
            MarketID=3222042112,
            StationName="Fan Horizons",
            StarSystem="Beta Sculptoris",
            Items=[],
        )

    async def test_watch_market_file_waits_until_market_file_appears(self):
        market_event = self._make_market_event()
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
            patch("builtins.open", mock_open(read_data=market_event.model_dump_json())),
            patch(
                "edceleste.services.game_watcher_service.asyncio.sleep",
                new=AsyncMock(side_effect=fake_sleep),
            ),
        ):
            await watcher.watch_side_file_and_publish_event("Market.json", MarketEvent)

        # The game only writes Market.json once the player opens the commodity
        # screen, so an absent file is normal and must not raise.
        self.mock_event_bus.publish.assert_awaited_once_with(market_event)

    async def test_watch_market_file_skips_invalid_market_json(self):
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
            await watcher.watch_side_file_and_publish_event("Market.json", MarketEvent)

        self.mock_event_bus.publish.assert_not_awaited()

    async def test_watch_market_file_only_republishes_on_change(self):
        market_event = self._make_market_event()
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
            patch("builtins.open", mock_open(read_data=market_event.model_dump_json())),
            patch(
                "edceleste.services.game_watcher_service.asyncio.sleep",
                new=AsyncMock(side_effect=fake_sleep),
            ),
        ):
            await watcher.watch_side_file_and_publish_event("Market.json", MarketEvent)

        self.mock_event_bus.publish.assert_awaited_once_with(market_event)

    async def test_start_starts_the_loading_task_then_a_task_per_side_file(
        self,
    ):
        """One task at the start (it loads the game state and follows the
        journal), a watcher for every file of SIDE_FILES and the watcher of
        newer journal files join it when the loading is done. Tests elsewhere
        stub the watcher out by name, so a rename must not go unnoticed."""
        watcher = self._make_watcher()

        with (
            patch.object(GameWatcherService, "watch_side_file_and_publish_event"),
            patch.object(
                GameWatcherService,
                "_GameWatcherService__follow_open_journal_file_and_publish_new_lines",
            ),
            patch(
                "edceleste.services.game_watcher_service.os.path.isfile",
                return_value=False,
            ),
            patch("builtins.open", mock_open(read_data="")),
        ):
            watcher.start_watcher_service()
            self.assertEqual(len(watcher._game_watcher_tasks), 1)

            await asyncio.sleep(0)

            self.assertEqual(len(watcher._game_watcher_tasks), 1 + len(SIDE_FILES) + 1)
            watcher.stop_watcher_service()

    def test_side_files_list_holds_the_five_game_files_in_loading_order(self):
        self.assertEqual(
            [
                ("Status.json", "Status"),
                ("Market.json", "Market"),
                ("NavRoute.json", "NavRoute"),
                ("Cargo.json", "Cargo"),
                ("ModulesInfo.json", "ModuleInfo"),
            ],
            [
                (file_name, event_model.model_fields["event"].annotation.__args__[0])
                for file_name, event_model in SIDE_FILES
            ],
        )

    def test_start_watcher_service_raises_and_starts_nothing_without_a_journal(self):
        self.mock_glob.return_value = []
        watcher = self._make_watcher()

        with self.assertRaises(FileNotFoundError):
            watcher.start_watcher_service()

        self.assertEqual(watcher._game_watcher_tasks, [])


class StartupLoadingOnDiskTest(unittest.IsolatedAsyncioTestCase):
    """Real temporary folder, real files and the real asyncio tasks of the
    watcher. Only the event bus is a recorder, so the order of what the watcher
    publishes can be checked."""

    LINE_TIMESTAMP = "2026-10-18T12:00:00Z"

    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.folder = Path(temp_dir.name)
        self.journal_file = self.folder / "Journal.2026-10-18T120000.01.log"
        self.journal_file.touch()

        self.published: list[tuple[str, bool]] = []
        self.published_events: list = []
        self.when_loading_is_finished = lambda: None
        event_bus = Mock()
        event_bus.publish = AsyncMock(side_effect=self._record_published_event)
        self.watcher = GameWatcherService(
            journal_path=str(self.folder),
            event_bus=event_bus,
            settings_service=Mock(),
        )

    async def asyncTearDown(self):
        # The watcher keeps the journal file open. Wait until its tasks are
        # gone, otherwise Windows cannot delete the temporary folder.
        watcher_tasks = list(self.watcher._game_watcher_tasks)
        self.watcher.stop_watcher_service()
        await asyncio.gather(*watcher_tasks, return_exceptions=True)

    async def _record_published_event(self, event) -> None:
        """Writes down (event name, is it a startup loading event)."""
        if isinstance(event, StartupLoadingFinishedEvent):
            self.published.append(("StartupLoadingFinished", False))
            self.when_loading_is_finished()
            return
        self.published.append((event.event, event.is_startup_loading))
        self.published_events.append(event)

    def _append_utf8_bytes_to_journal(self, line_bytes: bytes) -> None:
        """Adds raw bytes to the journal, so a test can write a byte that is
        not valid UTF-8."""
        with self.journal_file.open("ab") as journal:
            journal.write(line_bytes + b"\n")

    def _append_journal_line_with_text(self, event_name: str, text: str) -> None:
        """Adds a journal line like the game writes it: UTF-8 bytes, the
        letters as they are and not as \\u escapes."""
        line = (
            f'{{"timestamp":"{self.LINE_TIMESTAMP}","event":"{event_name}",'
            f'"Message":"{text}"}}'
        )
        self._append_utf8_bytes_to_journal(line.encode("utf-8"))

    def _append_journal_line(self, event_name: str) -> None:
        with self.journal_file.open("a", encoding="utf-8") as journal:
            journal.write(
                f'{{"timestamp":"{self.LINE_TIMESTAMP}","event":"{event_name}"}}\n'
            )

    def _write_status_file(self) -> None:
        (self.folder / "Status.json").write_text(
            f'{{"timestamp":"{self.LINE_TIMESTAMP}","event":"Status","Flags":0,"Flags2":0}}',
            encoding="utf-8",
        )

    def _write_market_file(self) -> None:
        (self.folder / "Market.json").write_text(
            f'{{"timestamp":"{self.LINE_TIMESTAMP}","event":"Market","MarketID":1,'
            '"StationName":"Fan Horizons","StarSystem":"Beta Sculptoris","Items":[]}',
            encoding="utf-8",
        )

    async def _wait_until(self, condition) -> None:
        """Fails the test with a TimeoutError when the condition does not come
        true within 5 s."""
        async with asyncio.timeout(5):
            while not condition():
                await asyncio.sleep(0.02)

    def _was_published(self, event_name: str) -> bool:
        return any(name == event_name for name, _ in self.published)

    async def test_loading_reads_the_journal_from_the_first_line_then_follows_new_lines(
        self,
    ):
        self._append_journal_line("OldEvent1")
        self._append_journal_line("OldEvent2")
        self._write_status_file()
        self._write_market_file()

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))
        self._append_journal_line("LiveEvent")
        await self._wait_until(lambda: self._was_published("LiveEvent"))

        self.assertEqual(
            self.published,
            [
                ("OldEvent1", True),
                ("OldEvent2", True),
                ("Status", True),
                ("Market", True),
                ("StartupLoadingFinished", False),
                ("LiveEvent", False),
            ],
        )

    async def test_side_files_loaded_at_startup_are_not_published_again_as_live(
        self,
    ):
        self._write_status_file()
        self._write_market_file()

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))
        # The side file watchers check once a second. Wait for more than one
        # round, so a second publication of the loaded files would show up.
        await asyncio.sleep(1.5)

        self.assertEqual(
            self.published,
            [
                ("Status", True),
                ("Market", True),
                ("StartupLoadingFinished", False),
            ],
        )

    async def test_side_file_rewritten_after_startup_is_published_as_live(self):
        self._write_status_file()

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))
        # Some file systems only change the modified time every few
        # milliseconds, so make the new version clearly newer.
        status_path = self.folder / "Status.json"
        newer_time = status_path.stat().st_mtime + 10
        self._write_status_file()
        os.utime(status_path, (newer_time, newer_time))
        await self._wait_until(lambda: ("Status", False) in self.published)

        self.assertEqual(
            self.published,
            [
                ("Status", True),
                ("StartupLoadingFinished", False),
                ("Status", False),
            ],
        )

    def _copy_sample_to_game_folder(self, sample_name: str, file_name: str) -> Path:
        """Puts a sample of tests/resources into the journal folder under the
        name the game gives it. Returns the path of the copy."""
        copy_path = self.folder / file_name
        shutil.copy(RESOURCES / sample_name, copy_path)
        return copy_path

    async def test_all_five_side_files_are_loaded_at_startup_and_not_published_again(
        self,
    ):
        self._write_status_file()
        self._write_market_file()
        self._copy_sample_to_game_folder("nav_route_plotted.json", "NavRoute.json")
        self._copy_sample_to_game_folder("cargo_with_inventory.json", "Cargo.json")
        self._copy_sample_to_game_folder("modules_info.json", "ModulesInfo.json")

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))
        # Wait for more than one round of the watchers (they check once a
        # second), so a second publication of a loaded file would show up.
        await asyncio.sleep(1.5)

        self.assertEqual(
            self.published,
            [
                ("Status", True),
                ("Market", True),
                ("NavRoute", True),
                ("Cargo", True),
                ("ModuleInfo", True),
                ("StartupLoadingFinished", False),
            ],
        )

    async def test_rewritten_nav_route_file_is_published_as_a_live_event(self):
        nav_route_path = self._copy_sample_to_game_folder(
            "nav_route_plotted.json", "NavRoute.json"
        )

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))
        # The pilot clears the route: the game rewrites the file, and the event
        # inside is called NavRouteClear.
        newer_time = nav_route_path.stat().st_mtime + 10
        self._copy_sample_to_game_folder("nav_route_clear.json", "NavRoute.json")
        os.utime(nav_route_path, (newer_time, newer_time))
        await self._wait_until(lambda: ("NavRouteClear", False) in self.published)

        self.assertEqual(
            self.published,
            [
                ("NavRoute", True),
                ("StartupLoadingFinished", False),
                ("NavRouteClear", False),
            ],
        )

    async def test_side_file_that_appears_after_startup_is_published_as_live(self):
        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))

        self._copy_sample_to_game_folder("cargo_with_inventory.json", "Cargo.json")
        await self._wait_until(lambda: ("Cargo", False) in self.published)

        self.assertEqual(
            self.published,
            [("StartupLoadingFinished", False), ("Cargo", False)],
        )

    async def test_line_written_between_loading_and_live_following_is_not_lost(self):
        self._append_journal_line("OldEvent")
        self.when_loading_is_finished = lambda: self._append_journal_line(
            "WrittenInBetween"
        )

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("WrittenInBetween"))

        self.assertEqual(
            self.published,
            [
                ("OldEvent", True),
                ("StartupLoadingFinished", False),
                ("WrittenInBetween", False),
            ],
        )

    async def test_an_empty_journal_without_side_files_finishes_loading_at_once(self):
        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))
        self._append_journal_line("FirstLiveEvent")
        await self._wait_until(lambda: self._was_published("FirstLiveEvent"))

        self.assertEqual(
            self.published,
            [("StartupLoadingFinished", False), ("FirstLiveEvent", False)],
        )

    # --- non-English letters in the game files ---

    async def test_journal_line_with_non_english_letters_does_not_stop_the_loading(
        self,
    ):
        self._append_journal_line_with_text("ReceiveText", "Привет, Łódź")
        self._append_journal_line("NextEvent")

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))

        self.assertEqual(
            self.published,
            [
                ("ReceiveText", True),
                ("NextEvent", True),
                ("StartupLoadingFinished", False),
            ],
        )

    async def test_commander_name_with_a_diaeresis_reaches_the_event_as_written(self):
        load_game_line = (
            f'{{"timestamp":"{self.LINE_TIMESTAMP}","event":"LoadGame","Commander":"Zoë",'
            '"FID":"F1","Horizons":true,"Odyssey":true,"Ship":"python","ShipID":1,'
            '"GameMode":"Solo","Credits":1,"Loan":0,"ShipName":"","ShipIdent":"",'
            '"FuelLevel":8.0,"FuelCapacity":8.0}'
        )
        self._append_utf8_bytes_to_journal(load_game_line.encode("utf-8"))

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))

        self.assertEqual(self.published_events[0].Commander, "Zoë")

    async def test_status_file_with_non_english_letters_does_not_stop_the_watcher(
        self,
    ):
        status_path = self.folder / "Status.json"
        status_path.write_text(
            f'{{"timestamp":"{self.LINE_TIMESTAMP}","event":"Status","Flags":0,'
            '"Destination":{"Name":"Łódź"}}',
            encoding="utf-8",
        )

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))
        newer_time = status_path.stat().st_mtime + 10
        self._write_status_file()
        os.utime(status_path, (newer_time, newer_time))
        await self._wait_until(lambda: ("Status", False) in self.published)

        self.assertEqual(
            self.published,
            [
                ("Status", True),
                ("StartupLoadingFinished", False),
                ("Status", False),
            ],
        )

    async def test_byte_that_is_not_valid_utf8_costs_one_character_not_the_session(
        self,
    ):
        self._append_utf8_bytes_to_journal(
            f'{{"timestamp":"{self.LINE_TIMESTAMP}","event":"Bro'.encode("utf-8")
            + b"\xff"
            + b'ken"}'
        )
        self._append_journal_line("NextEvent")

        self.watcher.start_watcher_service()
        await self._wait_until(lambda: self._was_published("StartupLoadingFinished"))

        self.assertEqual(
            self.published,
            [
                ("Bro�ken", True),
                ("NextEvent", True),
                ("StartupLoadingFinished", False),
            ],
        )

    async def test_game_files_are_opened_as_utf8_with_replacement(self):
        """Linux CI reads UTF-8 by default, so the content tests alone pass
        without the fix. This one checks the way the files are opened."""
        self._write_status_file()
        real_open = open

        with patch("builtins.open", wraps=real_open) as spy_open:
            self.watcher.start_watcher_service()
            await self._wait_until(
                lambda: self._was_published("StartupLoadingFinished")
            )

        opened_game_files = [
            call
            for call in spy_open.call_args_list
            if str(self.folder) in str(call.args[0])
        ]
        self.assertGreaterEqual(len(opened_game_files), 2)
        for call in opened_game_files:
            self.assertEqual(call.kwargs.get("encoding"), "utf-8")
            self.assertEqual(call.kwargs.get("errors"), "replace")


class JournalFilesOnDiskTest(unittest.TestCase):
    """Uses real temporary folders and no mocks. The glob mock of
    JournalWatcherTest returns a journal file for any pattern, so it can never
    show which file names the code accepts."""

    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.temp_root = Path(temp_dir.name)

    def _make_folder(self, folder_name: str, *file_names: str) -> str:
        """Creates the folder with one empty file per name and returns its path."""
        folder = self.temp_root / folder_name
        folder.mkdir()
        for file_name in file_names:
            (folder / file_name).touch()
        return str(folder)

    def _make_watcher(self, journal_path: str) -> GameWatcherService:
        return GameWatcherService(
            journal_path=journal_path,
            event_bus=Mock(),
            settings_service=Mock(),
        )

    def _names_of(self, file_paths: list[str]) -> list[str]:
        return sorted(os.path.basename(file_path) for file_path in file_paths)

    # --- find_journal_files ---

    def test_find_journal_files_finds_both_journal_name_formats(self):
        folder = self._make_folder(
            "journals",
            "Journal.2026-10-09T120000.01.log",
            "Journal.261009120000.01.log",
        )

        found = find_journal_files(folder)

        self.assertEqual(
            self._names_of(found),
            ["Journal.2026-10-09T120000.01.log", "Journal.261009120000.01.log"],
        )

    def test_find_journal_files_ignores_logs_with_other_names(self):
        folder = self._make_folder("logs", "netLog.2026-10-09.log", "app.log")

        self.assertEqual(find_journal_files(folder), [])

    def test_find_journal_files_matches_the_file_name_not_the_folder_path(self):
        folder = self._make_folder("MyJournals", "app.log")

        self.assertEqual(find_journal_files(folder), [])

    def test_find_journal_files_ignores_files_that_do_not_end_in_log(self):
        folder = self._make_folder(
            "journals", "Journal.2026.01.log.bak", "Journal.cache"
        )

        self.assertEqual(find_journal_files(folder), [])

    def test_find_journal_files_reads_a_folder_with_glob_characters_in_its_name(self):
        folder = self._make_folder("Elite [backup]", "Journal.2026.01.log")

        found = find_journal_files(folder)

        self.assertEqual(found, [os.path.join(folder, "Journal.2026.01.log")])

    def test_find_journal_files_returns_nothing_for_a_missing_folder(self):
        missing_folder = str(self.temp_root / "no-such-folder")

        self.assertEqual(find_journal_files(missing_folder), [])

    # --- validate_settings ---

    def test_validate_settings_rejects_a_folder_with_only_a_net_log(self):
        folder = self._make_folder("logs", "netLog.2026-10-09.log")
        watcher = self._make_watcher(folder)

        issue = watcher.validate_settings(_make_settings(journal_path=folder))

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "paths")
        self.assertEqual(issue.field, "journal_path")
        self.assertEqual(
            issue.message,
            f"No Elite Dangerous journal files (Journal*.log) found in '{folder}'.",
        )

    def test_validate_settings_rejects_a_journal_named_folder_with_only_app_log(self):
        folder = self._make_folder("MyJournals", "app.log")
        watcher = self._make_watcher(folder)

        issue = watcher.validate_settings(_make_settings(journal_path=folder))

        self.assertIsNotNone(issue)
        self.assertEqual(issue.field, "journal_path")

    def test_validate_settings_accepts_a_folder_with_a_journal_file(self):
        folder = self._make_folder("journals", "Journal.2026-10-09T120000.01.log")
        watcher = self._make_watcher(folder)

        issue = watcher.validate_settings(_make_settings(journal_path=folder))

        self.assertIsNone(issue)

    def test_validate_settings_keeps_the_message_for_a_missing_folder(self):
        missing_folder = str(self.temp_root / "no-such-folder")
        watcher = self._make_watcher(missing_folder)

        issue = watcher.validate_settings(_make_settings(journal_path=missing_folder))

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.message, f"Journal path '{missing_folder}' does not exist."
        )

    def test_validate_settings_keeps_the_message_for_an_empty_path(self):
        watcher = self._make_watcher("")

        issue = watcher.validate_settings(_make_settings(journal_path=""))

        self.assertIsNotNone(issue)
        self.assertEqual(issue.message, "Journal path is not set.")

    # --- the watcher ---

    def test_latest_journal_file_is_never_a_net_log_even_when_it_is_newer(self):
        folder = self._make_folder(
            "logs", "Journal.old.log", "Journal.new.log", "netLog.newest.log"
        )
        for file_name, modified_time in [
            ("Journal.old.log", 100),
            ("Journal.new.log", 200),
            ("netLog.newest.log", 300),
        ]:
            os.utime(os.path.join(folder, file_name), (modified_time, modified_time))
        watcher = self._make_watcher(folder)

        latest = watcher._GameWatcherService__get_latest_journal_filepath()  # type: ignore

        self.assertEqual(os.path.basename(latest), "Journal.new.log")

    def test_start_watcher_service_raises_for_a_folder_with_only_app_log(self):
        folder = self._make_folder("MyJournals", "app.log")
        watcher = self._make_watcher(folder)

        with self.assertRaises(FileNotFoundError):
            watcher.start_watcher_service()

        self.assertEqual(watcher._game_watcher_tasks, [])

    # --- one rule in both places ---

    def test_a_folder_passes_validation_exactly_when_the_watcher_can_start(self):
        folder_layouts = [
            # folder name, file names in it, is it a folder with a journal
            ("only_journal", ["Journal.2026-10-09T120000.01.log"], True),
            ("journal_and_net_log", ["netLog.1.log", "Journal.1.log"], True),
            ("only_net_log", ["netLog.1.log"], False),
            ("nothing_inside", [], False),
            ("MyJournals", ["app.log"], False),
        ]

        for folder_name, file_names, has_journal in folder_layouts:
            with self.subTest(folder=folder_name):
                folder = self._make_folder(folder_name, *file_names)
                watcher = self._make_watcher(folder)

                passes_validation = (
                    watcher.validate_settings(_make_settings(journal_path=folder))
                    is None
                )
                try:
                    watcher._GameWatcherService__get_latest_journal_filepath()  # type: ignore
                    watcher_can_start = True
                except FileNotFoundError:
                    watcher_can_start = False

                self.assertEqual(passes_validation, has_journal)
                self.assertEqual(watcher_can_start, has_journal)


class NewJournalFileOnDiskTest(unittest.IsolatedAsyncioTestCase):
    """Real journal files in a temporary folder. The watcher that looks for a
    newer journal file runs with a fake sleep, so no test waits for 3 s, and
    stop/start of the watcher are mocks that only count the restarts."""

    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.folder = Path(temp_dir.name)
        self.old_journal_file = self._write_journal_file(
            "Journal.2026-10-18T120000.01.log", [], modified_time=100
        )
        self.event_bus = AsyncMock()
        self.watcher = GameWatcherService(
            journal_path=str(self.folder),
            event_bus=self.event_bus,
            settings_service=Mock(),
        )
        # The watcher follows the old file, as after start_watcher_service.
        self.watcher._GameWatcherService__followed_journal_file_path = str(  # type: ignore
            self.old_journal_file
        )
        self.stop_watcher = self.enterContext(
            patch.object(self.watcher, "stop_watcher_service")
        )
        self.start_watcher = self.enterContext(
            patch.object(self.watcher, "start_watcher_service")
        )

    def _write_journal_file(
        self, file_name: str, lines: list[str], modified_time: int
    ) -> Path:
        journal_file = self.folder / file_name
        journal_file.write_text("\n".join(lines), encoding="utf-8")
        os.utime(journal_file, (modified_time, modified_time))
        return journal_file

    def _fileheader_line(self, part: int) -> str:
        return (
            '{ "timestamp":"2026-10-18T18:00:00Z", "event":"Fileheader", '
            f'"part":{part}, "language":"English/UK" }}'
        )

    def _is_later_part(self, journal_file: Path) -> bool:
        return self.watcher._GameWatcherService__is_later_part_of_a_split_session(  # type: ignore
            str(journal_file)
        )

    async def _look_for_a_newer_journal_file(self, in_second_check=None) -> None:
        """Runs the watcher of newer journal files. The first check happens at
        once, in_second_check (a function) runs between the first and the
        second check, and the loop ends after the second sleep."""
        sleep_calls = 0

        async def fake_sleep(_seconds):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls == 2 and in_second_check is not None:
                in_second_check()
            if sleep_calls >= 3:
                self.watcher.exit_signal = True

        with patch(
            "edceleste.services.game_watcher_service.asyncio.sleep",
            new=AsyncMock(side_effect=fake_sleep),
        ):
            look_for_newer_file = (
                self.watcher._GameWatcherService__restart_when_a_newer_journal_file_appears  # type: ignore
            )
            await look_for_newer_file()

    # --- __is_later_part_of_a_split_session ---

    def test_first_line_with_part_2_is_a_later_part_of_a_split_session(self):
        journal_file = self._write_journal_file(
            "Journal.part2.log", [self._fileheader_line(2)], modified_time=200
        )

        self.assertTrue(self._is_later_part(journal_file))

    def test_first_line_with_part_1_is_a_new_session(self):
        journal_file = self._write_journal_file(
            "Journal.part1.log", [self._fileheader_line(1)], modified_time=200
        )

        self.assertFalse(self._is_later_part(journal_file))

    def test_first_line_without_part_is_a_new_session(self):
        journal_file = self._write_journal_file(
            "Journal.nopart.log",
            ['{ "timestamp":"2026-10-18T18:00:00Z", "event":"Fileheader" }'],
            modified_time=200,
        )

        self.assertFalse(self._is_later_part(journal_file))

    def test_empty_or_broken_first_line_is_a_new_session(self):
        for case, lines in [("empty file", []), ("not json", ["{ half a line"])]:
            with self.subTest(case=case):
                journal_file = self._write_journal_file(
                    "Journal.broken.log", lines, modified_time=200
                )

                self.assertFalse(self._is_later_part(journal_file))

    def test_unreadable_journal_file_is_a_new_session(self):
        self.assertFalse(self._is_later_part(self.folder / "Journal.missing.log"))

    # --- __restart_when_a_newer_journal_file_appears ---

    async def test_new_session_file_publishes_new_game_session_event_then_restarts(
        self,
    ):
        self._write_journal_file(
            "Journal.2026-10-18T180000.01.log",
            [self._fileheader_line(1)],
            modified_time=200,
        )

        await self._look_for_a_newer_journal_file()

        self.event_bus.publish.assert_awaited_once()
        self.assertIsInstance(
            self.event_bus.publish.await_args.args[0], NewGameSessionEvent
        )
        self.stop_watcher.assert_called_once()
        self.start_watcher.assert_called_once()

    async def test_next_part_file_restarts_without_new_game_session_event(self):
        self._write_journal_file(
            "Journal.2026-10-18T120000.02.log",
            [self._fileheader_line(2)],
            modified_time=200,
        )

        await self._look_for_a_newer_journal_file()

        self.event_bus.publish.assert_not_called()
        self.stop_watcher.assert_called_once()
        self.start_watcher.assert_called_once()

    async def test_same_journal_file_changes_nothing(self):
        await self._look_for_a_newer_journal_file()

        self.event_bus.publish.assert_not_called()
        self.stop_watcher.assert_not_called()
        self.start_watcher.assert_not_called()

    async def test_folder_without_journal_files_is_ignored_until_one_appears(self):
        self.old_journal_file.unlink()

        def the_game_writes_a_new_journal_file():
            self._write_journal_file(
                "Journal.2026-10-18T180000.01.log",
                [self._fileheader_line(1)],
                modified_time=200,
            )

        await self._look_for_a_newer_journal_file(
            in_second_check=the_game_writes_a_new_journal_file
        )

        self.event_bus.publish.assert_awaited_once()
        self.start_watcher.assert_called_once()

    async def test_start_watcher_service_remembers_the_newest_journal_file(self):
        newest_journal_file = self._write_journal_file(
            "Journal.2026-10-18T180000.01.log",
            [self._fileheader_line(1)],
            modified_time=200,
        )

        with (
            patch("edceleste.services.game_watcher_service.asyncio.create_task"),
            patch.object(
                GameWatcherService,
                "_GameWatcherService__load_game_state_then_follow_the_game_files",
            ),
        ):
            # The real method, the instance one is mocked in setUp.
            GameWatcherService.start_watcher_service(self.watcher)
        await self._look_for_a_newer_journal_file()

        # The newest file is already followed, so there is nothing to restart.
        self.event_bus.publish.assert_not_called()
        self.stop_watcher.assert_not_called()
        self.assertEqual(
            self.watcher._GameWatcherService__followed_journal_file_path,  # type: ignore
            str(newest_journal_file),
        )


if __name__ == "__main__":
    unittest.main()
