"""The whole app runs for real, only what leaves the computer is faked:
config file, journal folder, keyboard, game window, speaker and the LLM.
"""

import shutil
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import yaml
from dependency_injector import providers
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.pilot import Pilot

from edceleste.containers.main_container import MODULES_USING_PROVIDE, Container
from edceleste.services.game_window import GameWindow
from edceleste.services.models.settings_model import (
    EventReactionModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from edceleste.services.settings_service import SettingsService
from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.system_check.system_check_screen import SystemCheckScreen
from edceleste.ui.ui_app import UIApp
from tests import TEST_BINDS_FILE_LOCATION, TEST_KNOWN_EVENTS_FILE_LOCATION

# Same size as the boards on the design canvas
SCREEN_SIZE = (200, 50)

NOT_SCRIPTED_ANSWER = "No answer was scripted for this test."


class FakeKeyboard:
    def __init__(self) -> None:
        self.keyboard_log: list[str] = []

    def keyDown(self, key: str) -> None:
        self.keyboard_log.append(f"keyDown {key}")

    def press(self, key: str) -> None:
        self.keyboard_log.append(f"press {key}")

    def keyUp(self, key: str) -> None:
        self.keyboard_log.append(f"keyUp {key}")


class FakeWindowsApiWithGameInFront:
    GAME_WINDOW = 1

    def FindWindowW(self, class_name: str | None, window_title: str) -> int:
        return self.GAME_WINDOW

    def GetForegroundWindow(self) -> int:
        return self.GAME_WINDOW

    def SetForegroundWindow(self, window: int) -> bool:
        return True


class FakeTtsProvider:
    def __init__(self, spoken_texts: list[str]) -> None:
        self.spoken_texts = spoken_texts

    async def synthesize(self, text: str) -> None:
        self.spoken_texts.append(text)

    def validate_settings(self, new_settings: SettingsModel) -> None:
        return None

    def reload_provider(self, new_settings: SettingsModel) -> None:
        pass


def recorded_journal_line(event_name: str) -> str:
    recorded_journal = TEST_KNOWN_EVENTS_FILE_LOCATION.read_text(encoding="utf-8")
    for line in recorded_journal.splitlines():
        if f'"event":"{event_name}"' in line.replace(" ", ""):
            return line
    raise ValueError(f"No {event_name} event in {TEST_KNOWN_EVENTS_FILE_LOCATION}")


def answer_preflight_connection_test(
    messages: list[ModelMessage], agent_info: AgentInfo
) -> ModelResponse:
    return ModelResponse(parts=[TextPart("OK")])


async def answer_not_scripted(messages: list[ModelMessage], agent_info: AgentInfo):
    yield NOT_SCRIPTED_ANSWER


StreamFunction = Callable[[list[ModelMessage], AgentInfo], AsyncIterator]


class EdCelesteTestEnvironment:
    def __init__(self, temp_folder: Path) -> None:
        journal_folder = temp_folder / "journal"
        journal_folder.mkdir()
        self.journal_file = journal_folder / "Journal.2026-10-05T120000.01.log"
        self.journal_file.touch()

        bindings_folder = temp_folder / "bindings"
        bindings_folder.mkdir()
        shutil.copy(TEST_BINDS_FILE_LOCATION, bindings_folder / "Custom.4.2.binds")

        settings = SettingsModel(
            paths=PathModel(
                journal_path=str(journal_folder),
                keybindings_path=str(bindings_folder),
            ),
            tts=TTSModel(volume=1.0),
            llm=LLMModel(
                system_prompt="You are Celeste, a ship computer.", user_prompt=""
            ),
            stt=SttModel(enabled=False, model="tiny.en"),
            # An empty dict turns every reaction off - an automatic LLM answer to
            # LoadGame would show up in the middle of a test
            event_reactions=EventReactionModel(reactions={}),
        )
        self.config_file = temp_folder / "config.yaml"
        self.config_file.write_text(yaml.safe_dump(settings.model_dump()))

        settings_service = SettingsService(config_path=self.config_file)
        settings_service.load_settings()

        self.container = Container()
        self.container.settings_service.override(providers.Object(settings_service))

        self.fake_keyboard = FakeKeyboard()
        keybinds_service = self.container.keybinds_service()
        keybinds_service.key_presser = self.fake_keyboard
        keybinds_service.game_window = GameWindow(
            windows_api=FakeWindowsApiWithGameInFront()
        )

        self.spoken_texts: list[str] = []
        fake_tts_provider = FakeTtsProvider(self.spoken_texts)
        self.container.tts_service().build_provider = lambda settings: fake_tts_provider

        self.use_scripted_model(answer_not_scripted)

        self.container.wire(modules=MODULES_USING_PROVIDE)

    def use_scripted_model(self, stream_function: StreamFunction) -> None:
        # function= answers the non streamed "Respond with only 'OK'" of the preflight
        scripted_model = FunctionModel(
            function=answer_preflight_connection_test, stream_function=stream_function
        )
        self.container.llm_service().build_model = lambda provider: scripted_model

    def run_app(self):
        return UIApp().run_test(size=SCREEN_SIZE)

    def append_journal_event(self, event_name: str) -> None:
        with self.journal_file.open("a", encoding="utf-8") as journal:
            journal.write(recorded_journal_line(event_name) + "\n")

    async def wait_until(
        self,
        pilot: Pilot,
        condition: Callable[[], bool],
        description: str,
        timeout_seconds: float = 5,
    ) -> None:
        # Not app.workers.wait_for_complete(): the dashboard workers stream
        # forever and never complete
        give_up_at = time.monotonic() + timeout_seconds
        while not condition():
            if time.monotonic() > give_up_at:
                pytest.fail(f"Waited {timeout_seconds} s for: {description}")
            await pilot.pause(0.05)

    async def boot_to_dashboard(self, pilot: Pilot) -> None:
        await self.wait_until(
            pilot,
            lambda: isinstance(pilot.app.screen, DashboardScreen),
            "the dashboard after the preflight",
        )
        # Lets the dashboard finish mounting and its workers start listening
        # before the game writes
        await pilot.pause()

        # Without a game state the LLM only answers "Game state is not set"
        self.append_journal_event("LoadGame")
        llm_service = self.container.llm_service()
        await self.wait_until(
            pilot,
            lambda: llm_service.game_state is not None,
            "the game state after LoadGame",
        )


@pytest.fixture
def anyio_backend():
    # Textual runs on asyncio only
    return "asyncio"


@pytest.fixture
async def edceleste(tmp_path, monkeypatch):
    monkeypatch.setattr(SystemCheckScreen, "SECONDS_BEFORE_DASHBOARD", 0)
    # A test can never reach a real LLM by mistake
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)

    environment = EdCelesteTestEnvironment(tmp_path)
    yield environment
    environment.container.unwire()
