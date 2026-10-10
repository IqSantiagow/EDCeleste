"""The whole app runs for real, only what leaves the computer is faked:
config file, journal folder, keyboard, game window, speaker, voices folder,
microphones, the LLM and the lists of LLM models and edge-tts voices.
"""

import shutil
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import allure
import numpy as np
import pytest
import yaml
from dependency_injector import providers
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.app import App
from textual.pilot import Pilot

from edceleste.containers.main_container import MODULES_USING_PROVIDE, Container
from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
)
from edceleste.services.game_window import GameWindow
from edceleste.services.models.settings_model import (
    EventReactionModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
    TtsProviderParams,
)
from edceleste.services import tts_service as tts_service_module
from edceleste.services.settings_service import SettingsService
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider
from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.dashboard.widgets.comms.widget_comms_entry import (
    WidgetCommsEntry,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_row import (
    WidgetShipLogRow,
)
from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from edceleste.ui.screens.system_check.system_check_screen import SystemCheckScreen
from edceleste.ui.ui_app import UIApp
from tests import TEST_BINDS_FILE_LOCATION, TEST_KNOWN_EVENTS_FILE_LOCATION

# Same size as the boards on the design canvas
SCREEN_SIZE = (200, 50)

NOT_SCRIPTED_ANSWER = "No answer was scripted for this test."
EDGE_VOICES_WITHOUT_NETWORK = ["en-GB-SoniaNeural", "en-US-AriaNeural"]
INSTINCT_MODEL_BYTES = 1_524_827_608


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


FAKE_SAMPLE_RATE = 24000


class FakeEdgeTtsProvider(EdgeTTSProvider):
    """The real Edge checks, but no network: it only remembers what it should say"""

    def __init__(self, spoken_texts: list[str]) -> None:
        self.spoken_texts = spoken_texts
        self.spoken_params: list[TtsProviderParams] = []
        self.spoken_profile_paths: list[Path | None] = []

    async def synthesize(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> tuple[np.ndarray, int]:
        self.spoken_texts.append(text)
        self.spoken_params.append(params)
        self.spoken_profile_paths.append(profile_path)
        return np.zeros(FAKE_SAMPLE_RATE, dtype=np.float32), FAKE_SAMPLE_RATE


class FakeChatterboxTtsProvider(ChatterboxTTSProvider):
    """The real Chatterbox checks, but no model and no GPU: a profile is a real
    file in the voices folder and speaking only remembers what it should say"""

    def __init__(self, spoken_texts: list[str]) -> None:
        super().__init__()
        self.spoken_texts = spoken_texts
        self.spoken_params: list[TtsProviderParams] = []
        self.spoken_profile_paths: list[Path | None] = []

    async def synthesize(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> tuple[np.ndarray, int]:
        if profile_path is not None and not profile_path.exists():
            raise FileNotFoundError(f"No voice profile at {profile_path}")
        self.spoken_texts.append(text)
        self.spoken_params.append(params)
        self.spoken_profile_paths.append(profile_path)
        return np.zeros(FAKE_SAMPLE_RATE, dtype=np.float32), FAKE_SAMPLE_RATE

    async def create_voice_profile(
        self,
        reference_audio_path: str,
        profile_path: Path,
        params: TtsProviderParams,
    ) -> None:
        profile_path.write_bytes(b"fake voice profile")

    def get_available_device(self) -> str:
        return "cpu"


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


def comms_entries(app: App, entry_type: str) -> list[str]:
    return [
        entry.content
        for entry in app.screen.query(WidgetCommsEntry)
        if entry.entry_type == entry_type
    ]


def ship_log_events(app: App) -> list[str]:
    rail_rows = app.screen.query_one("#ship-log-rail").query(WidgetShipLogRow)
    return [row.entry.event for row in rail_rows]


StreamFunction = Callable[[list[ModelMessage], AgentInfo], AsyncIterator]


class EdCelesteTestEnvironment:
    def __init__(self, temp_folder: Path) -> None:
        with allure.step("An empty journal and the test keybindings in a temp folder"):
            journal_folder = temp_folder / "journal"
            journal_folder.mkdir()
            self.journal_file = journal_folder / "Journal.2026-10-05T120000.01.log"
            self.status_file = journal_folder / "Status.json"
            self.journal_file.touch()

            bindings_folder = temp_folder / "bindings"
            bindings_folder.mkdir()
            shutil.copy(TEST_BINDS_FILE_LOCATION, bindings_folder / "Custom.4.2.binds")

        with allure.step("A config.yaml pointing at them, every event reaction off"):
            self.settings = SettingsModel(
                paths=PathModel(
                    journal_path=str(journal_folder),
                    keybindings_path=str(bindings_folder),
                ),
                tts=TTSModel(volume=1.0),
                llm=LLMModel(
                    system_prompt="You are Celeste, a ship computer.", user_prompt=""
                ),
                stt=SttModel(enabled=False, model="tiny.en"),
                # An empty dict turns every reaction off - an automatic LLM answer
                # to LoadGame would show up in the middle of a test
                event_reactions=EventReactionModel(reactions={}),
            )
            self.config_file = temp_folder / "config.yaml"
            self.save_config()

            settings_service = SettingsService(config_path=self.config_file)
            settings_service.load_settings()

            self.container = Container()
            self.container.settings_service.override(providers.Object(settings_service))

        with allure.step("The Instinct model in the temp folder, no Hugging Face Hub"):
            instinct_download_service = DecisionModelDownloadService(
                models_directory=temp_folder / "models"
            )
            instinct_download_service.fetch_download_size = lambda: INSTINCT_MODEL_BYTES
            self.container.decision_model_download_service.override(
                providers.Object(instinct_download_service)
            )

        with allure.step("A fake keyboard and a game window that is always in front"):
            self.fake_keyboard = FakeKeyboard()
            keybinds_service = self.container.keybinds_service()
            keybinds_service.key_presser = self.fake_keyboard
            keybinds_service.game_window = GameWindow(
                windows_api=FakeWindowsApiWithGameInFront()
            )

        with allure.step(
            "A fake speaker that remembers what Celeste says, voices without network"
        ):
            self.spoken_texts: list[str] = []
            self.fake_tts_providers = {
                "edge": FakeEdgeTtsProvider(self.spoken_texts),
                "chatterbox": FakeChatterboxTtsProvider(self.spoken_texts),
            }
            self.played_audio: list[dict] = []
            tts_service = self.container.tts_service()
            tts_service.build_provider = lambda provider_type: self.fake_tts_providers[
                provider_type
            ]
            tts_service.play_samples = self.remember_played_audio
            tts_service.fetch_edge_tts_voice_names = self.edge_voices_without_network

        with allure.step("LLM models and microphones listed without network"):
            self.container.llm_service().fetch_available_model_names = (
                self.llm_models_without_network
            )
            self.container.stt_service().get_stt_input_devices = lambda: [
                ("Test microphone", 0)
            ]

        with allure.step("An LLM that answers only what the test scripts"):
            self.use_scripted_model(answer_not_scripted)

        self.container.wire(modules=MODULES_USING_PROVIDE)

    def use_scripted_model(self, stream_function: StreamFunction) -> None:
        # function= answers the non streamed "Respond with only 'OK'" of the preflight
        scripted_model = FunctionModel(
            function=answer_preflight_connection_test, stream_function=stream_function
        )
        self.container.llm_service().build_model = lambda provider: scripted_model

    async def remember_played_audio(
        self, samples, sample_rate, volume, apply_voice_lab_effects
    ) -> None:
        self.played_audio.append({"volume": volume, "sample_rate": sample_rate})

    async def edge_voices_without_network(self) -> list[str]:
        return EDGE_VOICES_WITHOUT_NETWORK

    async def llm_models_without_network(self, provider=None) -> list[str]:
        return [self.settings.llm.provider.model]

    def save_config(self) -> None:
        self.config_file.write_text(yaml.safe_dump(self.settings.model_dump()))

    def save_tts_settings(self, tts_settings: TTSModel) -> None:
        self.settings.tts = tts_settings
        self.save_config()

    def allow_game_actions(self) -> None:
        self.settings.game_actions.enabled = True
        self.save_config()

    def react_to_event(self, event_name: str) -> None:
        self.settings.event_reactions.reactions[event_name] = True
        self.save_config()

    def run_app(self, show_notifications: bool = False):
        # Notifications are off by default: a toast on top of the screen could
        # cover what a test clicks. Tests that check a notification turn them on
        return UIApp().run_test(size=SCREEN_SIZE, notifications=show_notifications)

    def append_journal_event(self, event_name: str) -> None:
        with self.journal_file.open("a", encoding="utf-8") as journal:
            journal.write(recorded_journal_line(event_name) + "\n")

    def write_status_file(self) -> None:
        self.status_file.write_text(
            '{ "timestamp":"2026-10-05T12:00:00Z", "event":"Status", "Flags":0 }',
            encoding="utf-8",
        )

    async def wait_until(
        self,
        pilot: Pilot,
        condition: Callable[[], bool],
        description: str,
        timeout_seconds: float = 5,
    ) -> None:
        # Not app.workers.wait_for_complete(): the dashboard workers stream
        # forever and never complete
        with allure.step(f"Wait for {description}"):
            give_up_at = time.monotonic() + timeout_seconds
            while not condition():
                if time.monotonic() > give_up_at:
                    pytest.fail(f"Waited {timeout_seconds} s for: {description}")
                await pilot.pause(0.05)

    async def boot_to_dashboard(
        self, pilot: Pilot, step_keyword: str = "Given"
    ) -> None:
        # step_keyword is "And" when the test already has its own Given steps
        with allure.step(
            f"{step_keyword} Celeste is on the dashboard and the game is loaded"
        ):
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


async def open_settings_section(edceleste, pilot: Pilot, section_id: str) -> None:
    await pilot.press("ctrl+r")
    await edceleste.wait_until(
        pilot,
        lambda: isinstance(pilot.app.screen, SettingsScreen),
        "the settings screen",
    )
    await pilot.click(f"#settings-sections-column #{section_id}")
    await pilot.pause()


@pytest.fixture
def anyio_backend():
    # Textual runs on asyncio only
    return "asyncio"


@pytest.fixture
@allure.title("EDCeleste with everything that leaves the computer faked")
async def edceleste(tmp_path, monkeypatch):
    with allure.step("The preflight opens the dashboard without waiting"):
        monkeypatch.setattr(SystemCheckScreen, "SECONDS_BEFORE_DASHBOARD", 0)

    with allure.step("No request can reach a real LLM by mistake"):
        monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)

    with allure.step("The voice profiles go to a voices folder in the temp folder"):
        monkeypatch.setattr(tts_service_module, "VOICES_DIR", tmp_path / "voices")

    environment = EdCelesteTestEnvironment(tmp_path)
    environment.voices_folder = tmp_path / "voices"
    yield environment

    with allure.step("EDCeleste's services are unwired for the next test"):
        environment.container.unwire()
