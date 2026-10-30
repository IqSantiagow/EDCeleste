import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from edceleste.services.event_bus import EventBus
from edceleste.services.event_reactions_service import EventReactionsService
from edceleste.services.game_state_service import GameStateService
from edceleste.services.game_watcher_service import GameWatcherService
from edceleste.services.models.event_reaction_event import EventReactionEvent
from edceleste.services.models.game_events import FSDJumpEvent
from edceleste.services.models.startup_loading_finished_event import (
    StartupLoadingFinishedEvent,
)
from edceleste.services.settings_service import SettingsService
from tests.services.test_event_reactions_service import _make_settings

NEW_JOURNAL_FILE_CHECK_SECONDS_NAME = (
    "edceleste.services.game_watcher_service.NEW_JOURNAL_FILE_CHECK_SECONDS"
)
RECORDED_JOURNAL = Path(__file__).parents[2] / "resources" / "test_known_events.jsonl"

STATUS_FILE_CONTENT = (
    '{"timestamp":"2026-10-18T12:00:00Z","event":"Status","Flags":0,"Flags2":0,'
    '"Pips":[4,4,4],"Cargo":3.0,"Fuel":{"FuelMain":12.5,"FuelReservoir":0.4}}'
)


def recorded_journal_line(event_name: str) -> str:
    """One line of the journal recorded from the real game."""
    for line in RECORDED_JOURNAL.read_text(encoding="utf-8").splitlines():
        if f'"event":"{event_name}"' in line.replace(" ", ""):
            return line
    raise ValueError(f"No {event_name} event in {RECORDED_JOURNAL}")


class StartupLoadingIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """The watcher, the event bus, the game state and the event reactions are
    real, the game files are real files in a temporary folder. Every reaction
    is switched on, so a reaction that does not happen is the loading's work."""

    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.folder = Path(temp_dir.name)
        self.journal_file = self.folder / "Journal.2026-10-18T120000.01.log"
        self.journal_file.write_text(
            "\n".join(
                recorded_journal_line(event_name)
                for event_name in ["LoadGame", "StartJump", "FSDJump"]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.folder / "Status.json").write_text(STATUS_FILE_CONTENT, encoding="utf-8")
        self.running_watchers: list[GameWatcherService] = []

    async def asyncTearDown(self):
        # The watcher keeps the journal file open. Wait until its tasks are
        # gone, otherwise Windows cannot delete the temporary folder.
        for watcher in self.running_watchers:
            watcher_tasks = list(watcher._game_watcher_tasks)
            watcher.stop_watcher_service()
            await asyncio.gather(*watcher_tasks, return_exceptions=True)

    async def _start_the_app_on_the_game_files(self):
        """Builds the services like the app does and starts the watcher.
        Returns (game state service, reaction listener) once the loading is
        finished."""
        settings_service = Mock(spec=SettingsService)
        settings_service.get_settings.return_value = _make_settings(
            event_reactions={"LoadGame": True, "StartJump": True, "FSDJump": True}
        )
        event_bus = EventBus()
        game_state_service = GameStateService(event_bus)
        reactions_service = EventReactionsService(event_bus, settings_service)
        reactions_service.reload_service()
        reaction_listener = AsyncMock()
        event_bus.subscribe(EventReactionEvent, reaction_listener)
        loading_finished = asyncio.Event()

        async def remember_loading_is_finished(_event):
            loading_finished.set()

        event_bus.subscribe(StartupLoadingFinishedEvent, remember_loading_is_finished)
        watcher = GameWatcherService(
            journal_path=str(self.folder),
            event_bus=event_bus,
            settings_service=settings_service,
        )
        self.running_watchers.append(watcher)

        watcher.start_watcher_service()
        async with asyncio.timeout(5):
            await loading_finished.wait()
        return game_state_service, reaction_listener

    async def test_loading_builds_the_state_without_reactions_then_a_live_event_reacts(
        self,
    ):
        (
            game_state_service,
            reaction_listener,
        ) = await self._start_the_app_on_the_game_files()

        game_state = game_state_service.get_game_state_projection()
        self.assertIn("Commander name is SANTIAGOW.", game_state)
        self.assertIn("Beta Sculptoris", game_state)
        self.assertIn("Current fuel level is: 12.5.", game_state)
        reaction_listener.assert_not_called()

        with self.journal_file.open("a", encoding="utf-8") as journal:
            journal.write(recorded_journal_line("FSDJump") + "\n")
        async with asyncio.timeout(5):
            while not reaction_listener.called:
                await asyncio.sleep(0.02)

        reaction_listener.assert_called_once()
        reaction = reaction_listener.call_args.args[0]
        self.assertIsInstance(reaction.event, FSDJumpEvent)
        self.assertFalse(reaction.event.is_startup_loading)

    async def test_starting_twice_on_the_same_game_files_gives_the_same_game_state(
        self,
    ):
        first_service, first_listener = await self._start_the_app_on_the_game_files()
        first_state = first_service.get_game_state_projection()
        self.running_watchers[0].stop_watcher_service()

        second_service, second_listener = await self._start_the_app_on_the_game_files()

        self.assertNotEqual(first_state, "")
        self.assertEqual(first_state, second_service.get_game_state_projection())
        first_listener.assert_not_called()
        second_listener.assert_not_called()

    def _write_newer_journal_file(self, lines: list[str]) -> Path:
        """What the game does when it starts again: a new journal file, newer
        than the one the app is following."""
        newer_journal_file = self.folder / "Journal.2026-10-18T180000.01.log"
        newer_journal_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.utime(newer_journal_file, (time.time() + 60, time.time() + 60))
        return newer_journal_file

    async def _wait_until(self, condition) -> None:
        async with asyncio.timeout(5):
            while not condition():
                await asyncio.sleep(0.02)

    async def test_game_restart_forgets_the_old_session_and_follows_the_new_journal(
        self,
    ):
        with patch(NEW_JOURNAL_FILE_CHECK_SECONDS_NAME, 0.05):
            (
                game_state_service,
                reaction_listener,
            ) = await self._start_the_app_on_the_game_files()
            self.assertIn(
                "Beta Sculptoris", game_state_service.get_game_state_projection()
            )

            newer_journal_file = self._write_newer_journal_file(
                [recorded_journal_line("LoadGame")]
            )
            await self._wait_until(
                lambda: (
                    "Beta Sculptoris"
                    not in game_state_service.get_game_state_projection()
                )
            )

            # The new file is loaded silently, then it is followed live.
            game_state = game_state_service.get_game_state_projection()
            self.assertIn("Commander name is SANTIAGOW.", game_state)
            reaction_listener.assert_not_called()
            with newer_journal_file.open("a", encoding="utf-8") as journal:
                journal.write(recorded_journal_line("FSDJump") + "\n")
            await self._wait_until(lambda: reaction_listener.called)
            self.assertIn(
                "Beta Sculptoris", game_state_service.get_game_state_projection()
            )

    async def test_next_part_of_a_long_session_keeps_the_state(self):
        with patch(NEW_JOURNAL_FILE_CHECK_SECONDS_NAME, 0.05):
            (
                game_state_service,
                reaction_listener,
            ) = await self._start_the_app_on_the_game_files()

            newer_journal_file = self._write_newer_journal_file(
                [
                    '{ "timestamp":"2026-10-18T18:00:00Z", "event":"Fileheader", '
                    '"part":2, "language":"English/UK", "Odyssey":true }',
                    recorded_journal_line("Location"),
                ]
            )
            # The Location line of the new part is loaded silently, its system
            # shows that the part is followed.
            await self._wait_until(
                lambda: "HIP 115966" in game_state_service.get_game_state_projection()
            )
            reaction_listener.assert_not_called()
            with newer_journal_file.open("a", encoding="utf-8") as journal:
                journal.write(recorded_journal_line("StartJump") + "\n")
            await self._wait_until(lambda: reaction_listener.called)

            # The commander comes only from the old part's LoadGame.
            game_state = game_state_service.get_game_state_projection()
            self.assertIn("Commander name is SANTIAGOW.", game_state)


if __name__ == "__main__":
    unittest.main()
