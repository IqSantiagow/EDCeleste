"""The whole app runs for real, only what leaves the computer is faked:
config file, journal folder, keyboard, game window, speaker, voices folder,
microphones, the Instinct decision model, the LLM and the lists of LLM models
and edge-tts voices.
"""

import asyncio
import enum
import shutil
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import allure
import numpy as np
import pytest
import whisper
import yaml
from dependency_injector import providers
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from textual.app import App
from textual.pilot import Pilot

from edceleste.containers.main_container import MODULES_USING_PROVIDE, Container
from edceleste.services.decision_model_download_service import (
    DOWNLOAD_COMPLETE_FILE,
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
from edceleste.services import hotkey_service as hotkey_service_module
from edceleste.services import speaker_service as speaker_service_module
from edceleste.services import tts_service as tts_service_module
from edceleste.services.settings_service import SettingsService
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider
from edceleste.services.tts_providers.pocket_tts_provider import PocketTTSProvider
from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.dashboard.widgets.comms.widget_comms_entry import (
    WidgetCommsEntry,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_row import (
    WidgetShipLogRow,
)
from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from edceleste.ui.screens.settings.widgets.stt.bind_hotkey_modal_screen import (
    BindHotkeyModalScreen,
)
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


class FakeWindowsApiWithoutGame:
    def FindWindowW(self, class_name: str | None, window_title: str) -> int:
        return 0

    def GetForegroundWindow(self) -> int:
        return 0

    def SetForegroundWindow(self, window: int) -> bool:
        return False


NO_ACTION_CHOSEN = "none"
# A model that was never let go must not keep the test run from ending
SLOW_MODEL_GIVES_UP_AFTER_SECONDS = 3


class FakeDecider:
    """The Instinct decision model without GPU and weights. It picks the action
    the test scripted for a pilot message and 'none' for every other message.
    A test can make it slow: it then answers a command only after the test
    lets it"""

    def __init__(self, device: str) -> None:
        self.dev = device
        self.choices_by_message: dict[str, str] = {}
        self.messages_asked: list[str] = []
        self.model_may_answer: threading.Event | None = None

    def make_the_model_slow(self) -> None:
        self.model_may_answer = threading.Event()

    def let_the_model_answer(self) -> None:
        if self.model_may_answer is not None:
            self.model_may_answer.set()

    def system_one(self, state: dict, questions: dict) -> dict:
        if "action" not in questions:
            # The warm up question at start-up, its answer is thrown away
            return {
                "answers": {
                    name: {"choice": "false", "probabilities": {"false": 1.0}}
                    for name in questions
                }
            }

        pilot_message = state["pilot_said"]
        self.messages_asked.append(pilot_message)
        if self.model_may_answer is not None:
            self.model_may_answer.wait(timeout=SLOW_MODEL_GIVES_UP_AFTER_SECONDS)
        choice = self.choices_by_message.get(pilot_message, NO_ACTION_CHOSEN)
        return {
            "answers": {"action": {"choice": choice, "probabilities": {choice: 1.0}}}
        }


FAKE_SAMPLE_RATE = 24000
# Three pieces of a tenth of a second, every one at its own level, so a test
# sees the order of the pieces in what the speaker played
FAKE_VOICE_PIECE_LEVELS = (0.1, 0.2, 0.3)
FAKE_VOICE_PIECE_SAMPLES = FAKE_SAMPLE_RATE // 10


# A speaker that never gets released must not keep the test run from ending
HELD_SPEAKER_GIVES_UP_AFTER_SECONDS = 3


class FakeSpeaker:
    """The speaker of a voice that is played while it is still being made,
    without hardware: it remembers every block of audio it was given, in order.
    A test can hold it: after the given number of blocks the speaker takes no
    more until the test lets it go on, like a real speaker that needs time to
    play. Only the first hold counts"""

    def __init__(self) -> None:
        self.sample_rate: int | None = None
        self.times_opened = 0
        self.times_closed = 0
        self.times_aborted = 0
        self.blocks: list[np.ndarray] = []
        self.is_holding = False
        self.blocks_before_the_hold: int | None = None
        self.playing_may_go_on = threading.Event()

    def hold_playback_after(self, blocks: int) -> None:
        self.blocks_before_the_hold = blocks
        self.playing_may_go_on.clear()

    def let_playing_go_on(self) -> None:
        self.blocks_before_the_hold = None
        self.playing_may_go_on.set()

    def open(self, sample_rate: int) -> "FakeSpeaker":
        self.sample_rate = sample_rate
        self.times_opened += 1
        return self

    def __enter__(self) -> "FakeSpeaker":
        return self

    def __exit__(self, *error_details) -> None:
        self.times_closed += 1

    def write(self, samples: np.ndarray) -> None:
        if self.blocks_before_the_hold == len(self.blocks):
            self.is_holding = True
            self.playing_may_go_on.wait(timeout=HELD_SPEAKER_GIVES_UP_AFTER_SECONDS)
            self.is_holding = False
            self.blocks_before_the_hold = None
        self.blocks.append(samples.copy())

    def abort(self) -> None:
        """The speaker throws away what it still holds: the Commander hears
        silence at once"""
        self.times_aborted += 1

    def everything_played(self) -> np.ndarray:
        if not self.blocks:
            return np.zeros((0, 2), dtype=np.float32)
        return np.concatenate(self.blocks)


class FakeClock:
    """The clock of the speech queue. It runs like the real one, and a test can
    move it on, so waiting five seconds takes no time"""

    def __init__(self) -> None:
        self.seconds_moved_on = 0.0

    def monotonic(self) -> float:
        return time.monotonic() + self.seconds_moved_on

    def move_on(self, seconds: float) -> None:
        self.seconds_moved_on += seconds

    def go_back_to_real_time(self) -> None:
        """What is queued from now on is not older than it really is"""
        self.seconds_moved_on = 0.0


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
    file in the voices folder and speaking only remembers what it should say.
    A test can make the model slow: it then learns a new voice only after the
    test lets it finish.
    It speaks in pieces like the real one on a GPU (can_stream and the sample
    rate are the real ones, so only a saved device "cuda" streams). A test can
    make the voice slow (only the first piece comes until the test lets it
    finish) and make it break once, after its first piece"""

    def __init__(self, spoken_texts: list[str]) -> None:
        super().__init__()
        self.spoken_texts = spoken_texts
        self.spoken_params: list[TtsProviderParams] = []
        self.spoken_profile_paths: list[Path | None] = []
        self.model_started_learning_a_voice = False
        self.model_may_finish: asyncio.Event | None = None
        self.voice_pieces: list[np.ndarray] = [
            np.full(FAKE_VOICE_PIECE_SAMPLES, level, dtype=np.float32)
            for level in FAKE_VOICE_PIECE_LEVELS
        ]
        self.voice_may_continue: asyncio.Event | None = None
        self.voice_breaks_once = False

    def make_the_model_slow(self) -> None:
        self.model_may_finish = asyncio.Event()

    def let_the_model_finish(self) -> None:
        if self.model_may_finish is not None:
            self.model_may_finish.set()

    def make_the_voice_slow(self) -> None:
        self.voice_may_continue = asyncio.Event()

    def let_the_voice_finish(self) -> None:
        if self.voice_may_continue is not None:
            self.voice_may_continue.set()

    def break_the_voice_once(self) -> None:
        self.voice_breaks_once = True

    async def synthesize_stream(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> AsyncIterator[np.ndarray]:
        if profile_path is not None and not profile_path.exists():
            raise FileNotFoundError(f"Voice profile not found: {profile_path}")
        self.spoken_texts.append(text)
        self.spoken_params.append(params)
        self.spoken_profile_paths.append(profile_path)
        for piece_number, piece in enumerate(self.voice_pieces):
            if piece_number == 1:
                if self.voice_breaks_once:
                    self.voice_breaks_once = False
                    raise RuntimeError("CUDA out of memory")
                if self.voice_may_continue is not None:
                    await self.voice_may_continue.wait()
            yield piece

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
        self.model_started_learning_a_voice = True
        if self.model_may_finish is not None:
            await self.model_may_finish.wait()
        profile_path.write_bytes(b"fake voice profile")

    def get_available_device(self) -> str:
        return "cpu"


class FakePocketTtsProvider(PocketTTSProvider):
    """The real Pocket TTS checks (folder and file type of a profile, speaking
    in pieces), but no model and no download: a profile is a real file in the
    voices folder and speaking only remembers what it should say. It speaks in
    the same three pieces as the fake Chatterbox"""

    def __init__(self, spoken_texts: list[str]) -> None:
        super().__init__()
        self.spoken_texts = spoken_texts
        self.spoken_params: list[TtsProviderParams] = []
        self.spoken_profile_paths: list[Path | None] = []
        self.voice_pieces: list[np.ndarray] = [
            np.full(FAKE_VOICE_PIECE_SAMPLES, level, dtype=np.float32)
            for level in FAKE_VOICE_PIECE_LEVELS
        ]

    async def synthesize_stream(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> AsyncIterator[np.ndarray]:
        if profile_path is not None and not profile_path.exists():
            raise FileNotFoundError(f"Voice profile not found: {profile_path}")
        self.spoken_texts.append(text)
        self.spoken_params.append(params)
        self.spoken_profile_paths.append(profile_path)
        for piece in self.voice_pieces:
            yield piece

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


class FakeMouseButton(enum.Enum):
    """The mouse buttons of pynput, named the same way: str() gives 'Button.x1'"""

    left = 1
    right = 2
    middle = 3
    x1 = 4
    x2 = 5

    def __str__(self) -> str:
        return f"Button.{self.name}"


class FakePynputListener:
    """A pynput listener without a hook in the system: it only remembers the
    functions it should call and whether it still listens"""

    def __init__(self, on_press=None, on_release=None, on_click=None) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.on_click = on_click
        self.is_listening = False

    def start(self) -> None:
        self.is_listening = True

    def stop(self) -> None:
        self.is_listening = False


class FakeGlobalKeysAndMouse:
    """The keys and mouse buttons the Commander presses anywhere on the computer,
    also while the game has focus. pynput is replaced by a fake with no hook in
    the system. A key reaches every listener that still listens, like a real
    global hook, and on a thread of its own like pynput does"""

    def __init__(self) -> None:
        self.keyboard_listeners: list[FakePynputListener] = []
        self.mouse_listeners: list[FakePynputListener] = []

    def build_keyboard_listener(self, on_press=None, on_release=None):
        listener = FakePynputListener(on_press=on_press, on_release=on_release)
        self.keyboard_listeners.append(listener)
        return listener

    def build_mouse_listener(self, on_click=None):
        listener = FakePynputListener(on_click=on_click)
        self.mouse_listeners.append(listener)
        return listener

    def build_pynput_modules(self) -> dict[str, ModuleType]:
        keyboard = ModuleType("pynput.keyboard")
        keyboard.Listener = self.build_keyboard_listener
        mouse = ModuleType("pynput.mouse")
        mouse.Listener = self.build_mouse_listener
        mouse.Button = FakeMouseButton
        pynput = ModuleType("pynput")
        pynput.keyboard = keyboard
        pynput.mouse = mouse
        return {
            "pynput": pynput,
            "pynput.keyboard": keyboard,
            "pynput.mouse": mouse,
        }

    async def hold_key(self, key_name: str) -> None:
        """key_name is as pynput prints it: 'Key.f9', "'l'" """

        def tell_the_listeners() -> None:
            for listener in self.keyboard_listeners:
                if listener.is_listening and listener.on_press is not None:
                    listener.on_press(key_name)

        await asyncio.to_thread(tell_the_listeners)

    async def release_key(self, key_name: str) -> None:
        def tell_the_listeners() -> None:
            for listener in self.keyboard_listeners:
                if listener.is_listening and listener.on_release is not None:
                    listener.on_release(key_name)

        await asyncio.to_thread(tell_the_listeners)

    async def click_mouse_button(self, button_name: str) -> None:
        """button_name is 'left', 'right', 'middle', 'x1' or 'x2'"""
        button = FakeMouseButton[button_name]

        def tell_the_listeners() -> None:
            for is_pressed in (True, False):
                for listener in self.mouse_listeners:
                    if listener.is_listening and listener.on_click is not None:
                        listener.on_click(0, 0, button, is_pressed)

        await asyncio.to_thread(tell_the_listeners)


class FakeMicrophoneStream:
    def __init__(self, microphone: "FakeMicrophone", callback) -> None:
        self.microphone = microphone
        self.callback = callback

    def start(self) -> None:
        self.microphone.times_opened += 1
        one_tenth_of_a_second = np.zeros((1600, 1), dtype=np.float32)
        self.callback(one_tenth_of_a_second, 1600, None, None)

    def stop(self) -> None:
        pass

    def close(self) -> None:
        self.microphone.times_closed += 1


class FakeMicrophone:
    """A microphone and a Whisper model without hardware and weights: whatever
    the Commander records, Whisper hears the text the test scripted"""

    def __init__(self) -> None:
        self.heard_text = ""
        self.times_opened = 0
        self.times_closed = 0

    def hears(self, text: str) -> None:
        self.heard_text = text

    def build_sounddevice_module(self) -> ModuleType:
        sounddevice = ModuleType("sounddevice")
        sounddevice.InputStream = lambda callback, **settings: FakeMicrophoneStream(
            self, callback
        )
        return sounddevice

    def build_whisper_model(self) -> SimpleNamespace:
        return SimpleNamespace(
            transcribe=lambda audio, **settings: {"text": f" {self.heard_text} "}
        )


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


async def send_comms_message(pilot: Pilot, message: str) -> None:
    await pilot.click("#comms-input")
    await pilot.press(*message)
    await pilot.press("enter")


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
            self.instinct_download_service = DecisionModelDownloadService(
                models_directory=temp_folder / "models"
            )
            self.instinct_download_service.fetch_download_size = lambda: (
                INSTINCT_MODEL_BYTES
            )
            self.container.decision_model_download_service.override(
                providers.Object(self.instinct_download_service)
            )

        with allure.step("A fake keyboard and a game window that is always in front"):
            self.fake_keyboard = FakeKeyboard()
            keybinds_service = self.container.keybinds_service()
            keybinds_service.key_presser = self.fake_keyboard
            keybinds_service.game_window = GameWindow(
                windows_api=FakeWindowsApiWithGameInFront()
            )

        with allure.step(
            "A fake speaker that remembers what Celeste says and plays, voices "
            "without network"
        ):
            self.spoken_texts: list[str] = []
            self.fake_tts_providers = {
                "edge": FakeEdgeTtsProvider(self.spoken_texts),
                "chatterbox": FakeChatterboxTtsProvider(self.spoken_texts),
                "pocket": FakePocketTtsProvider(self.spoken_texts),
            }
            self.played_audio: list[dict] = []
            tts_service = self.container.tts_service()
            tts_service.build_provider = lambda provider_type: self.fake_tts_providers[
                provider_type
            ]
            # The methods are private, so they are reached by their mangled names
            tts_service._TTSService__play_samples = self.remember_played_audio
            self.fake_speaker = FakeSpeaker()
            speaker_service = self.container.speaker_service()
            speaker_service._SpeakerService__open_speaker = self.fake_speaker.open
            tts_service.fetch_edge_tts_voice_names = self.edge_voices_without_network

        with allure.step("LLM models and microphones listed without network"):
            self.model_list_requests = 0
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
        self, samples, sample_rate, volume, with_ship_effect=False
    ) -> None:
        self.played_audio.append(
            {
                "volume": volume,
                "sample_rate": sample_rate,
                "samples": samples,
                "with_ship_effect": with_ship_effect,
            }
        )

    async def edge_voices_without_network(self) -> list[str]:
        return EDGE_VOICES_WITHOUT_NETWORK

    async def llm_models_without_network(self, provider=None) -> list[str]:
        self.model_list_requests += 1
        return [self.settings.llm.provider.model]

    def save_config(self) -> None:
        self.config_file.write_text(yaml.safe_dump(self.settings.model_dump()))

    def save_tts_settings(self, tts_settings: TTSModel) -> None:
        self.settings.tts = tts_settings
        self.save_config()

    def turn_speech_to_text_on(self, push_to_talk_key: str | None = None) -> None:
        self.settings.stt.enabled = True
        self.settings.stt.hotkey = push_to_talk_key
        self.save_config()

    def allow_game_actions(self) -> None:
        self.settings.game_actions.enabled = True
        self.save_config()

    def turn_instinct_on(self, device: str = "cuda") -> FakeDecider:
        # The model counts as downloaded and loaded: no Hub, no download, no GPU.
        # The preflight still runs its real start-up question through the fake
        self.settings.llm.instinct.enabled = True
        self.save_config()

        model_folder = self.instinct_download_service.model_folder
        model_folder.mkdir(parents=True)
        (model_folder / DOWNLOAD_COMPLETE_FILE).write_text("test")

        fake_decider = FakeDecider(device)
        self.container.instinct_service().decider = fake_decider
        return fake_decider

    def close_the_game_window(self) -> None:
        self.container.keybinds_service().game_window = GameWindow(
            windows_api=FakeWindowsApiWithoutGame()
        )

    def react_to_event(self, event_name: str) -> None:
        self.settings.event_reactions.reactions[event_name] = True
        self.save_config()

    @asynccontextmanager
    async def run_app(self, show_notifications: bool = False):
        """Runs EDCeleste in a Textual pilot for the test.

        Side effects: when the test body ends, passed or failed, the screen the
        Commander would see is attached to the Allure report as an SVG picture.
        """
        # Notifications are off by default: a toast on top of the screen could
        # cover what a test clicks. Tests that check a notification turn them on
        async with UIApp().run_test(
            size=SCREEN_SIZE, notifications=show_notifications
        ) as pilot:
            try:
                yield pilot
            finally:
                allure.attach(
                    pilot.app.export_screenshot(),
                    name="The screen at the end of the test",
                    attachment_type=allure.attachment_type.SVG,
                )

    def append_journal_event(self, event_name: str) -> None:
        with self.journal_file.open("a", encoding="utf-8") as journal:
            journal.write(recorded_journal_line(event_name) + "\n")

    def write_status_file(
        self,
        fuel_main: float | None = None,
        cargo: float | None = None,
        flags: int = 0,
    ) -> None:
        # Without arguments the file is the same as it always was. flags is the
        # bit field of the game: 1 docked, 2 landed, 16 supercruise
        extra_fields = ""
        if cargo is not None:
            extra_fields += f', "Cargo":{cargo}'
        if fuel_main is not None:
            extra_fields += (
                f', "Fuel":{{ "FuelMain":{fuel_main}, "FuelReservoir":0.4 }}'
            )
        self.status_file.write_text(
            '{ "timestamp":"2026-10-05T12:00:00Z", "event":"Status", '
            f'"Flags":{flags}{extra_fields} }}',
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

    async def click_when_ready(self, pilot: Pilot, selector: str) -> None:
        # Textual ignores a click on a button that still plays its press
        # animation (class "-active", 0.2 s). A second click on the same button
        # is lost when the screen reacts faster than that, which fast fakes do
        await self.wait_until(
            pilot,
            lambda: len(pilot.app.screen.query(selector)) == 1,
            f"{selector} to be on the screen",
        )
        button = pilot.app.screen.query_one(selector)
        await self.wait_until(
            pilot,
            lambda: not button.has_class("-active"),
            f"{selector} to finish its press animation",
        )
        await pilot.click(selector)

    async def open_dashboard(self, pilot: Pilot, step_keyword: str = "Given") -> None:
        # Unlike boot_to_dashboard it writes nothing to the journal: a test that
        # starts Celeste on game files written before, must not add a live LoadGame
        with allure.step(f"{step_keyword} Celeste starts and the dashboard opens"):
            await self.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, DashboardScreen),
                "the dashboard after the preflight",
            )
            # Lets the dashboard finish mounting and its workers start listening
            await pilot.pause()

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


async def open_stt_settings(edceleste, pilot: Pilot) -> None:
    await open_settings_section(edceleste, pilot, "settings-stt")
    await edceleste.wait_until(
        pilot,
        lambda: len(pilot.app.screen.query("#hotkey-bind-button")) == 1,
        "the Push-to-talk key row",
    )


async def click_bind_and_wait_for_the_dialog(edceleste, pilot: Pilot) -> None:
    await edceleste.click_when_ready(pilot, "#hotkey-bind-button")
    await edceleste.wait_until(
        pilot,
        # The screen is pushed before its widgets are mounted
        lambda: (
            isinstance(pilot.app.screen, BindHotkeyModalScreen)
            and len(pilot.app.screen.query("#bind-hotkey-confirm-button")) == 1
        ),
        "the BIND HOTKEY dialog",
    )


def key_shown_in_the_dialog(app: App) -> str | None:
    # query, not query_one: while the dialog is drawn again it has no Label
    caught_key_labels = app.screen.query("#bind-hotkey-key")
    if len(caught_key_labels) != 1:
        return None
    # The Label is mounted a moment before the buttons below it, a slow runner
    # can see the key and still find no button
    if len(app.screen.query("#bind-hotkey-confirm-button")) != 1:
        return None
    return str(caught_key_labels.first().content)


SECONDS_TO_WAIT_FOR_LAYOUT = 5


def build_click_that_waits_for_layout(original_click):
    # pilot.click("<selector>") aims at the region the widget has when the click
    # starts. A widget that is mounted but not laid out yet has an empty region
    # at (0, 0), so the click lands in the corner of the screen and is lost
    # without any error. That happens on a busy machine to the Clone voice
    # buttons and to the input of the file picker. Waiting until the target has
    # a region is the same thing a pilot does by looking at the screen
    async def click(self: Pilot, widget=None, *arguments, **keyword_arguments):
        if isinstance(widget, str):
            give_up_at = time.monotonic() + SECONDS_TO_WAIT_FOR_LAYOUT
            while time.monotonic() < give_up_at:
                matches = self.app.screen.query(widget)
                if matches and matches.first().region.area > 0:
                    break
                await self.pause(0.05)
        return await original_click(self, widget, *arguments, **keyword_arguments)

    return click


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

    with allure.step("A click waits until its target is on the screen"):
        monkeypatch.setattr(
            Pilot, "click", build_click_that_waits_for_layout(Pilot.click)
        )

    with allure.step(
        "A fake keyboard and mouse that the Commander uses anywhere on the computer"
    ):
        global_keys_and_mouse = FakeGlobalKeysAndMouse()
        for name, module in global_keys_and_mouse.build_pynput_modules().items():
            monkeypatch.setitem(sys.modules, name, module)
        # The real service listens only on Windows, the tests run everywhere
        monkeypatch.setattr(
            hotkey_service_module, "sys", SimpleNamespace(platform="win32")
        )

    with allure.step("A clock for the speech queue that the test can move on"):
        clock = FakeClock()
        # Only the reading of the time is replaced: QueuedSpeech notes the time
        # it was queued with the real clock, so moving on makes every speech
        # that waits look older
        monkeypatch.setattr(
            speaker_service_module, "time", SimpleNamespace(monotonic=clock.monotonic)
        )

    with allure.step("A fake microphone and a Whisper that hears what the test says"):
        microphone = FakeMicrophone()
        monkeypatch.setitem(
            sys.modules, "sounddevice", microphone.build_sounddevice_module()
        )
        monkeypatch.setattr(
            whisper, "load_model", lambda model_name: microphone.build_whisper_model()
        )

    environment = EdCelesteTestEnvironment(tmp_path)
    environment.global_keys_and_mouse = global_keys_and_mouse
    environment.microphone = microphone
    environment.clock = clock
    environment.voices_folder = tmp_path / "voices"
    # The profiles of Chatterbox, the engine the e2e voices are made for
    environment.chatterbox_voices_folder = environment.voices_folder / "chatterbox"
    environment.pocket_voices_folder = environment.voices_folder / "pocket"
    yield environment

    with allure.step("EDCeleste's services are unwired for the next test"):
        environment.container.unwire()
