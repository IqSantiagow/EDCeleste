import asyncio
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import httpx
import numpy as np
from pydantic_ai import ToolReturn

from edceleste.services import instinct_service
from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
    DownloadCancelled,
)
from edceleste.services.instinct_service import (
    CLASSES_FILE,
    CONFIDENCE_THRESHOLD,
    MAX_TOKENS,
    MODEL_FILE,
    TOKENIZER_FILE,
    InstinctService,
    ModelNotDownloaded,
    describe_top_scores,
)
from edceleste.services.models.instinct_status import (
    DownloadProgress,
    InstinctFailure,
    InstinctModelState,
)
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.fast_command_reply import FastCommandReply
from edceleste.services.models.reply_texts import ACTIONS_SAID_BY_GAME_STATE
from edceleste.services.models.reply_text import REPLY_TEXTS
from edceleste.services.models.settings_model import (
    GameActionsModel,
    InstinctModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from tests.use_cases.dashboard.game_stats_fixtures import (
    make_game_stats_snapshot,
    make_ship_stats,
)

MODEL_BYTES = 1_500_000_000
MODULE = "edceleste.services.instinct_service"


def make_settings(enabled: bool, game_actions_enabled: bool = False) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(volume=1.0),
        llm=LLMModel(
            system_prompt="sp",
            user_prompt="",
            instinct=InstinctModel(enabled=enabled),
        ),
        stt=SttModel(model="tiny.en"),
        game_actions=GameActionsModel(enabled=game_actions_enabled),
    )


class FakeDownloadService:
    def __init__(self, downloaded: bool = False, error: Exception | None = None):
        self.downloaded = downloaded
        self.error = error
        self.cancel_requested = False
        self.may_finish = asyncio.Event()
        self.may_finish.set()

    def is_model_downloaded(self) -> bool:
        return self.downloaded

    def cancel_download(self) -> None:
        self.cancel_requested = True

    async def download_model(self):
        self.cancel_requested = False
        yield DownloadProgress(bytes_done=630_000_000, bytes_total=MODEL_BYTES)
        await self.may_finish.wait()
        if self.cancel_requested:
            raise DownloadCancelled("cancelled")
        if self.error:
            raise self.error
        self.downloaded = True
        yield DownloadProgress(bytes_done=MODEL_BYTES, bytes_total=MODEL_BYTES)


class FakeKeybinds:
    """Stands for KeybindService: which actions have a key."""

    def __init__(
        self,
        bound_actions: set[EdAction] | None = None,
        keys_loaded: bool = True,
    ):
        self.bound_actions = set(EdAction) if bound_actions is None else bound_actions
        self.keys_loaded = keys_loaded

    def is_bound(self, action: EdAction) -> bool:
        if not self.keys_loaded:
            raise KeyError(action)
        return action in self.bound_actions


class FakePerformGameAction:
    """Stands for the PerformGameAction tool: records every action it gets and
    answers with a fixed ToolReturn, or raises. By default the key was pressed."""

    def __init__(
        self,
        result: ToolReturn | None = None,
        error: Exception | None = None,
    ):
        self.result = result or ToolReturn(
            return_value="Performed game action", metadata={"is_error": False}
        )
        self.error = error
        self.executed: list[EdAction] = []

    async def perform_game_action(self, action: EdAction) -> ToolReturn:
        self.executed.append(action)
        if self.error is not None:
            raise self.error
        return self.result


class FakeGameState:
    def __init__(self, text: str = "Commander name is NOVA.", ship=None):
        self.text = text
        self.ship = ship or make_ship_stats()

    def get_game_state_projection(self) -> str:
        return self.text

    def get_game_stats(self):
        return make_game_stats_snapshot(ship=self.ship)


class FakeScorer:
    """Stands for InstinctService.score_every_class, the run of the model. Gives
    the chosen class a high score and every other class a low one, and records
    every message, also how many ran at the same time."""

    def __init__(
        self,
        choice: str = "none",
        error: Exception | None = None,
    ):
        self.choice = choice
        self.error = error
        self.seconds_per_call = 0.0
        self.release = threading.Event()  # clear it to keep the model busy
        self.release.set()
        self.calls: list[str] = []
        self.running_now = 0
        self.most_running_at_once = 0
        self.counter_lock = threading.Lock()

    def __call__(self, pilot_message: str) -> dict[str, float]:
        with self.counter_lock:
            self.calls.append(pilot_message)
            self.running_now += 1
            self.most_running_at_once = max(self.most_running_at_once, self.running_now)
        try:
            self.release.wait(5)
            time.sleep(self.seconds_per_call)
            if self.error is not None:
                raise self.error
            scores = {name: 0.01 for name in [*(a.value for a in EdAction), "none"]}
            scores[self.choice] = 0.9
            return scores
        finally:
            with self.counter_lock:
                self.running_now -= 1


def make_fast_command_service(
    enabled: bool = True,
    game_actions_enabled: bool = True,
    choice: str = "LandingGearToggle",
    keybinds: FakeKeybinds | None = None,
    game_state_text: str = "Commander name is NOVA.",
    model_error: Exception | None = None,
    perform_game_action: FakePerformGameAction | None = None,
    ship=None,
) -> InstinctService:
    """A service that is ready to decide: on, model loaded, game actions on,
    every action has a key, the tool presses it. Each test breaks exactly one of
    these."""
    settings_service = Mock()
    settings_service.get_settings.return_value = make_settings(
        enabled, game_actions_enabled=game_actions_enabled
    )
    service = InstinctService(
        settings_service,
        FakeDownloadService(downloaded=True),
        keybinds or FakeKeybinds(),
        FakeGameState(game_state_text, ship),
        perform_game_action or FakePerformGameAction(),  # type: ignore[arg-type]
    )
    service.enabled = enabled
    service.session = object()  # type: ignore[assignment]
    service.score_every_class = FakeScorer(choice=choice, error=model_error)  # type: ignore[method-assign]
    return service


class InstinctServiceTest(unittest.IsolatedAsyncioTestCase):
    def make_service(self, enabled: bool, download_service: FakeDownloadService):
        self.settings_service = Mock()
        self.settings_service.get_settings.return_value = make_settings(enabled)
        service = InstinctService(
            self.settings_service, download_service, Mock(), Mock(), Mock()
        )
        service.warm_up = MagicMock()  # never load the real model in these tests
        return service

    async def wait_for_background_work(self, service: InstinctService) -> None:
        if service.background_task:
            await service.background_task

    async def test_disabled_instinct_unloads_the_model_and_downloads_nothing(self):
        download_service = FakeDownloadService()
        service = self.make_service(enabled=False, download_service=download_service)
        service.session = MagicMock()

        service.reload_service()

        self.assertIsNone(service.session)
        self.assertIsNone(service.background_task)
        self.assertEqual(service.get_model_state(), InstinctModelState.NOT_DOWNLOADED)

    async def test_enabled_instinct_downloads_a_missing_model_and_loads_it(self):
        download_service = FakeDownloadService()
        service = self.make_service(enabled=True, download_service=download_service)

        service.reload_service()
        await self.wait_for_background_work(service)

        self.assertTrue(download_service.downloaded)
        service.warm_up.assert_called_once_with()
        self.assertEqual(service.get_model_state(), InstinctModelState.READY)

    async def test_enabled_instinct_with_a_downloaded_model_only_loads_it(self):
        service = self.make_service(
            enabled=True, download_service=FakeDownloadService(downloaded=True)
        )

        service.reload_service()
        await self.wait_for_background_work(service)

        service.warm_up.assert_called_once_with()

    async def test_state_is_downloading_with_progress_while_the_download_runs(self):
        download_service = FakeDownloadService()
        download_service.may_finish.clear()
        service = self.make_service(enabled=True, download_service=download_service)

        service.reload_service()
        await asyncio.sleep(0)

        status = service.get_status()
        self.assertEqual(status.state, InstinctModelState.DOWNLOADING)
        self.assertEqual(
            status.download_progress,
            DownloadProgress(bytes_done=630_000_000, bytes_total=MODEL_BYTES),
        )
        download_service.may_finish.set()
        await self.wait_for_background_work(service)

    async def test_download_button_with_instinct_off_downloads_without_loading(self):
        download_service = FakeDownloadService()
        service = self.make_service(enabled=False, download_service=download_service)
        service.reload_service()

        service.download_and_load_model_in_background()
        await self.wait_for_background_work(service)

        self.assertTrue(download_service.downloaded)
        service.warm_up.assert_not_called()

    async def test_cancel_returns_to_not_downloaded_without_a_failure(self):
        download_service = FakeDownloadService()
        download_service.may_finish.clear()
        service = self.make_service(enabled=True, download_service=download_service)
        service.reload_service()
        await asyncio.sleep(0)

        service.cancel_download()
        download_service.may_finish.set()
        await self.wait_for_background_work(service)

        self.assertEqual(service.get_model_state(), InstinctModelState.NOT_DOWNLOADED)
        self.assertIsNone(service.get_status().failure)

    async def test_network_failure_is_a_download_failure_with_a_short_reason(self):
        request = httpx.Request("GET", "https://huggingface.co")
        download_service = FakeDownloadService(
            error=httpx.ConnectError("getaddrinfo failed", request=request)
        )
        service = self.make_service(enabled=True, download_service=download_service)

        service.reload_service()
        await self.wait_for_background_work(service)

        self.assertEqual(service.get_model_state(), InstinctModelState.FAILED)
        self.assertEqual(
            service.get_status().failure,
            InstinctFailure("download", "no connection to huggingface.co"),
        )

    async def test_a_model_that_does_not_load_is_a_load_failure(self):
        service = self.make_service(
            enabled=True, download_service=FakeDownloadService(downloaded=True)
        )
        service.warm_up.side_effect = RuntimeError("broken model file")

        service.reload_service()
        await self.wait_for_background_work(service)

        self.assertEqual(
            service.get_status().failure, InstinctFailure("load", "broken model file")
        )

    async def test_retry_clears_the_last_failure(self):
        download_service = FakeDownloadService(error=RuntimeError("disk full"))
        service = self.make_service(enabled=True, download_service=download_service)
        service.reload_service()
        await self.wait_for_background_work(service)
        download_service.error = None

        service.download_and_load_model_in_background()
        await self.wait_for_background_work(service)

        self.assertEqual(service.get_model_state(), InstinctModelState.READY)

    async def test_download_size_is_none_when_the_hub_cannot_be_reached(self):
        download_service = FakeDownloadService()
        download_service.fetch_download_size = Mock(side_effect=OSError("offline"))
        service = self.make_service(enabled=True, download_service=download_service)

        self.assertIsNone(service.fetch_download_size())

    async def test_download_size_is_asked_from_the_hub_only_once(self):
        download_service = FakeDownloadService()
        download_service.fetch_download_size = Mock(return_value=MODEL_BYTES)
        service = self.make_service(enabled=True, download_service=download_service)

        service.fetch_download_size()
        size = service.fetch_download_size()

        self.assertEqual(size, MODEL_BYTES)
        download_service.fetch_download_size.assert_called_once_with()


class InstinctColdStartTest(unittest.IsolatedAsyncioTestCase):
    def make_service(self, enabled: bool, download_service: FakeDownloadService):
        settings_service = Mock()
        settings_service.get_settings.return_value = make_settings(enabled)
        service = InstinctService(
            settings_service, download_service, Mock(), Mock(), Mock()
        )
        service.warm_up = MagicMock()
        return service

    async def test_disabled_instinct_reports_disabled(self):
        service = self.make_service(False, FakeDownloadService())

        statuses = [status async for status in service.cold_start()]

        self.assertTrue(statuses[-1].completed)
        self.assertTrue(statuses[-1].is_disabled)

    async def test_first_start_shows_download_progress_then_ok(self):
        download_service = FakeDownloadService()
        download_service.may_finish.clear()
        service = self.make_service(True, download_service)

        statuses = []
        async for status in service.cold_start():
            statuses.append(status)
            if status.progress_text:
                download_service.may_finish.set()

        progress_texts = [status.progress_text for status in statuses]
        self.assertIn("Downloading model 42% · 630 MB of 1.5 GB", progress_texts)
        self.assertTrue(statuses[-1].completed)
        self.assertIsNone(statuses[-1].message)

    async def test_failed_download_is_a_warning_not_a_failure(self):
        request = httpx.Request("GET", "https://huggingface.co")
        error = httpx.ConnectError("getaddrinfo failed", request=request)
        service = self.make_service(True, FakeDownloadService(error=error))

        statuses = [status async for status in service.cold_start()]

        self.assertTrue(statuses[-1].is_warning)
        self.assertFalse(statuses[-1].is_critical)
        self.assertEqual(
            statuses[-1].message,
            "model download failed (no connection to huggingface.co). "
            "Commands go through Celeste.",
        )

    async def test_a_loaded_model_gives_no_warning(self):
        service = self.make_service(True, FakeDownloadService(downloaded=True))
        service.session = object()  # type: ignore[assignment]

        statuses = [status async for status in service.cold_start()]

        self.assertTrue(statuses[-1].completed)
        self.assertFalse(statuses[-1].is_warning)
        self.assertIsNone(statuses[-1].message)


class InstinctModelLoadingTest(unittest.TestCase):
    def setUp(self):
        self.model_folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.model_folder)
        (self.model_folder / CLASSES_FILE).write_text(
            json.dumps(["Supercruise", "none"]), encoding="utf-8"
        )
        self.download_service = MagicMock(spec=DecisionModelDownloadService)
        self.download_service.model_folder = self.model_folder
        self.download_service.is_model_downloaded.return_value = True
        self.service = InstinctService(
            Mock(), self.download_service, Mock(), Mock(), Mock()
        )
        tokenizer_patcher = patch(f"{MODULE}.Tokenizer")
        self.tokenizer_class = tokenizer_patcher.start()
        self.addCleanup(tokenizer_patcher.stop)
        onnxruntime_patcher = patch(f"{MODULE}.onnxruntime")
        self.onnxruntime = onnxruntime_patcher.start()
        self.addCleanup(onnxruntime_patcher.stop)

    def test_load_model_reads_the_tokenizer_the_classes_and_the_model(self):
        self.service.load_model_once()

        self.tokenizer_class.from_file.assert_called_once_with(
            str(self.model_folder / TOKENIZER_FILE)
        )
        self.tokenizer_class.from_file.return_value.enable_truncation.assert_called_once_with(
            MAX_TOKENS
        )
        self.assertEqual(self.service.class_names, ["Supercruise", "none"])
        self.assertEqual(
            self.onnxruntime.InferenceSession.call_args.args[0],
            str(self.model_folder / MODEL_FILE),
        )
        self.assertIs(
            self.service.session, self.onnxruntime.InferenceSession.return_value
        )

    def test_load_model_runs_on_one_cpu_thread(self):
        self.service.load_model_once()

        self.assertEqual(
            self.onnxruntime.SessionOptions.return_value.intra_op_num_threads, 1
        )
        self.assertEqual(
            self.onnxruntime.InferenceSession.call_args.kwargs["providers"],
            ["CPUExecutionProvider"],
        )

    def test_load_model_loads_only_once(self):
        self.service.load_model_once()
        self.service.load_model_once()

        self.onnxruntime.InferenceSession.assert_called_once()

    def test_load_model_refuses_a_model_that_is_not_downloaded(self):
        self.download_service.is_model_downloaded.return_value = False

        with self.assertRaises(ModelNotDownloaded):
            self.service.load_model_once()

        self.onnxruntime.InferenceSession.assert_not_called()

    def test_load_model_stays_unloaded_when_a_file_is_missing(self):
        (self.model_folder / CLASSES_FILE).unlink()

        with self.assertRaises(FileNotFoundError):
            self.service.load_model_once()

        self.assertIsNone(self.service.session)

    def test_unload_model_forgets_the_model(self):
        self.service.session = MagicMock()

        self.service.unload_model()

        self.assertIsNone(self.service.session)

    def test_unload_model_does_nothing_when_no_model_is_loaded(self):
        self.service.unload_model()

        self.assertIsNone(self.service.session)


class ScoreEveryClassTest(unittest.TestCase):
    def make_service(self, logits: list[float]) -> InstinctService:
        service = InstinctService(Mock(), Mock(), Mock(), Mock(), Mock())
        service.class_names = ["Supercruise", "LandingGearToggle", "none"]
        service.tokenizer = MagicMock()
        service.tokenizer.encode.return_value = MagicMock(
            ids=[101, 7, 102], attention_mask=[1, 1, 1]
        )
        service.session = MagicMock()
        service.session.run.return_value = [np.array([logits])]
        return service

    def test_gives_the_softmax_of_the_logits_by_class_name(self):
        service = self.make_service([2.0, 1.0, 0.0])

        scores = service.score_every_class("engage supercruise")

        exponents = np.exp([2.0, 1.0, 0.0])
        expected = exponents / exponents.sum()
        self.assertEqual(list(scores), ["Supercruise", "LandingGearToggle", "none"])
        self.assertAlmostEqual(scores["Supercruise"], expected[0])
        self.assertAlmostEqual(sum(scores.values()), 1.0)

    def test_feeds_the_ids_and_the_attention_mask_of_the_message(self):
        service = self.make_service([0.0, 0.0, 0.0])

        service.score_every_class("engage supercruise")

        service.tokenizer.encode.assert_called_once_with("engage supercruise")
        feed = service.session.run.call_args.args[1]
        self.assertEqual(feed["input_ids"].tolist(), [[101, 7, 102]])
        self.assertEqual(feed["attention_mask"].tolist(), [[1, 1, 1]])

    def test_does_not_overflow_on_big_logits(self):
        service = self.make_service([1000.0, 0.0, 0.0])

        scores = service.score_every_class("engage supercruise")

        self.assertAlmostEqual(scores["Supercruise"], 1.0)


class IsModuleEnabledTest(unittest.TestCase):
    # Every test starts from a service that is ready and breaks one condition

    def test_is_true_when_on_and_loaded(self):
        service = make_fast_command_service()

        self.assertTrue(service.is_module_enabled())

    def test_is_false_when_instinct_is_disabled(self):
        service = make_fast_command_service(enabled=False)

        self.assertFalse(service.is_module_enabled())

    def test_is_false_when_the_model_is_not_loaded(self):
        service = make_fast_command_service()
        service.session = None

        self.assertFalse(service.is_module_enabled())

    def test_does_not_care_about_the_game_actions_switch(self):
        service = make_fast_command_service(game_actions_enabled=False)

        self.assertTrue(service.is_module_enabled())


class CanDecideCommandsTest(unittest.TestCase):
    def test_is_true_when_game_actions_are_on(self):
        service = make_fast_command_service(game_actions_enabled=True)

        self.assertTrue(service.can_decide_commands())

    def test_is_false_when_game_actions_are_off(self):
        service = make_fast_command_service(game_actions_enabled=False)

        self.assertFalse(service.can_decide_commands())

    def test_does_not_care_whether_the_model_is_ready(self):
        service = make_fast_command_service(enabled=False, game_actions_enabled=True)

        self.assertTrue(service.can_decide_commands())


class FindActionsWithAKeyTest(unittest.TestCase):
    def test_lists_only_actions_with_a_key_in_the_order_of_ed_action(self):
        # The set is given in the opposite order to prove EdAction sets the order
        keybinds = FakeKeybinds(
            bound_actions={EdAction.LANDING_GEAR_TOGGLE, EdAction.SUPERCRUISE}
        )
        service = make_fast_command_service(keybinds=keybinds)

        self.assertEqual(
            service.find_actions_with_a_key(),
            [EdAction.SUPERCRUISE, EdAction.LANDING_GEAR_TOGGLE],
        )

    def test_is_empty_when_the_keybinds_are_not_loaded(self):
        service = make_fast_command_service(keybinds=FakeKeybinds(keys_loaded=False))

        self.assertEqual(service.find_actions_with_a_key(), [])


class AskWhichActionTest(unittest.TestCase):
    def test_sends_the_message_and_the_offered_actions_and_returns_the_answer(self):
        service = make_fast_command_service(choice="Supercruise")
        offered = [EdAction.SUPERCRUISE, EdAction.LANDING_GEAR_TOGGLE]

        answer = service.pick_offered_action("engage supercruise", offered)

        self.assertEqual(answer["choice"], "Supercruise")
        self.assertEqual(
            service.score_every_class.calls,  # type: ignore[attr-defined]
            ["engage supercruise"],
        )
        self.assertEqual(
            list(answer["probabilities"]),
            ["Supercruise", "LandingGearToggle", "none"],
        )

    def test_only_the_offered_actions_compete(self):
        service = make_fast_command_service(choice="LandingGearToggle")

        answer = service.pick_offered_action(
            "deploy landing gear", [EdAction.SUPERCRUISE]
        )

        # The best class is not offered, so the best offered option is "none"
        self.assertEqual(list(answer["probabilities"]), ["Supercruise", "none"])
        self.assertEqual(answer["choice"], "none")

    def test_an_offered_action_the_model_does_not_know_is_left_out(self):
        service = make_fast_command_service()
        service.score_every_class = lambda pilot_message: {  # type: ignore[method-assign]
            "Supercruise": 0.9,
            "none": 0.01,
        }

        answer = service.pick_offered_action(
            "deploy landing gear", [EdAction.SUPERCRUISE, EdAction.LANDING_GEAR_TOGGLE]
        )

        self.assertEqual(list(answer["probabilities"]), ["Supercruise", "none"])

    def test_a_best_score_under_the_threshold_is_none(self):
        service = make_fast_command_service()
        service.score_every_class = lambda pilot_message: {  # type: ignore[method-assign]
            "Supercruise": CONFIDENCE_THRESHOLD - 0.01,
            "none": 0.01,
        }

        answer = service.pick_offered_action("hmm", [EdAction.SUPERCRUISE])

        self.assertEqual(answer["choice"], "none")

    def test_a_best_score_at_the_threshold_is_the_action(self):
        service = make_fast_command_service()
        service.score_every_class = lambda pilot_message: {  # type: ignore[method-assign]
            "Supercruise": CONFIDENCE_THRESHOLD,
            "none": 0.01,
        }

        answer = service.pick_offered_action(
            "engage supercruise", [EdAction.SUPERCRUISE]
        )

        self.assertEqual(answer["choice"], "Supercruise")

    def test_an_empty_offer_is_none(self):
        service = make_fast_command_service(choice="Supercruise")

        answer = service.pick_offered_action("engage supercruise", [])

        self.assertEqual(answer["choice"], "none")
        self.assertEqual(list(answer["probabilities"]), ["none"])

    def test_logs_the_message_the_best_scores_and_the_time(self):
        service = make_fast_command_service(choice="Supercruise")

        with self.assertLogs(instinct_service.logger, level="INFO") as logs:
            service.pick_offered_action("engage supercruise", [EdAction.SUPERCRUISE])

        self.assertEqual(len(logs.output), 1)
        self.assertIn("'engage supercruise'", logs.output[0])
        self.assertIn("Supercruise 0.90", logs.output[0])
        self.assertIn(" ms", logs.output[0])

    def test_loads_the_model_first_when_it_is_not_loaded(self):
        service = make_fast_command_service(choice="Supercruise")
        service.load_model_once = MagicMock()  # type: ignore[method-assign]

        service.pick_offered_action("engage supercruise", [EdAction.SUPERCRUISE])

        service.load_model_once.assert_called_once_with()


class WarmUpTest(unittest.TestCase):
    def test_loads_the_model_and_runs_one_message_through_it(self):
        service = make_fast_command_service()
        service.load_model_once = MagicMock()  # type: ignore[method-assign]

        service.warm_up()

        service.load_model_once.assert_called_once_with()
        self.assertEqual(
            service.score_every_class.calls,  # type: ignore[attr-defined]
            ["deploy hardpoints"],
        )

    def test_works_without_a_game_state_and_without_keys(self):
        # The warm up asks no real command, so it does not need either
        service = make_fast_command_service(
            game_state_text="", keybinds=FakeKeybinds(bound_actions=set())
        )

        service.warm_up()

        self.assertEqual(len(service.score_every_class.calls), 1)  # type: ignore[attr-defined]

    def test_refuses_a_model_that_is_not_downloaded(self):
        service = make_fast_command_service()
        service.session = None
        service.download_service.is_model_downloaded = MagicMock(return_value=False)  # type: ignore[method-assign]

        with self.assertRaises(ModelNotDownloaded):
            service.warm_up()


class DescribeTopScoresTest(unittest.TestCase):
    def test_lists_the_best_three_options_best_first(self):
        scores = {"a": 0.10, "b": 0.70, "c": 0.15, "d": 0.05}

        self.assertEqual(describe_top_scores(scores), "b 0.70, c 0.15, a 0.10")


class TryFastCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_gives_the_chosen_action_to_the_tool_and_returns_the_reply(self):
        service = make_fast_command_service(choice="LandingGearToggle")

        reply = await service.try_fast_command("deploy landing gear")

        # The gear is said by the game state a moment later, so it is not spoken here
        self.assertEqual(reply, FastCommandReply("Landing gear deployed", False))
        self.assertEqual(
            service.perform_game_action.executed, [EdAction.LANDING_GEAR_TOGGLE]
        )
        self.assertEqual(
            service.score_every_class.calls,  # type: ignore[attr-defined]
            ["deploy landing gear"],
        )

    async def test_logs_one_line_with_the_message_the_action_and_the_best_scores(self):
        service = make_fast_command_service(choice="LandingGearToggle")

        with self.assertLogs(instinct_service.logger, level="INFO") as logs:
            await service.try_fast_command("deploy landing gear")

        fast_command_lines = [line for line in logs.output if "Fast command" in line]
        self.assertEqual(len(fast_command_lines), 1)
        line = fast_command_lines[0]
        self.assertIn("'deploy landing gear'", line)
        self.assertIn("Instinct pressed LandingGearToggle in ", line)
        self.assertIn("LandingGearToggle 0.90", line)  # the best score, first

    async def test_returns_none_and_presses_nothing_when_the_model_chooses_none(self):
        service = make_fast_command_service(choice="none")

        # "none" is a normal answer, not an error that happens to give None too
        with self.assertNoLogs(instinct_service.logger, level="ERROR"):
            reply = await service.try_fast_command("how much fuel do I have")

        self.assertIsNone(reply)
        self.assertEqual(len(service.score_every_class.calls), 1)  # type: ignore[attr-defined]
        self.assertEqual(service.perform_game_action.executed, [])

    async def test_does_not_ask_the_model_when_it_cannot_decide(self):
        service = make_fast_command_service(enabled=False)

        reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(service.score_every_class.calls, [])  # type: ignore[attr-defined]

    async def test_does_not_ask_the_model_when_no_action_has_a_key(self):
        service = make_fast_command_service(keybinds=FakeKeybinds(bound_actions=set()))

        reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(service.score_every_class.calls, [])  # type: ignore[attr-defined]

    async def test_does_not_ask_the_model_when_the_game_state_is_empty(self):
        service = make_fast_command_service(game_state_text="")

        reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(service.score_every_class.calls, [])  # type: ignore[attr-defined]

    async def test_returns_none_when_the_model_runs_out_of_time(self):
        service = make_fast_command_service(choice="LandingGearToggle")
        service.score_every_class.release.clear()  # type: ignore[attr-defined]

        with (
            patch.object(instinct_service, "FAST_COMMAND_TIMEOUT_SECONDS", 0.2),
            self.assertLogs(instinct_service.logger, level="WARNING"),
        ):
            reply = await service.try_fast_command("deploy landing gear")

        # Checked before the model is let go: its late answer would press the key
        self.assertIsNone(reply)
        self.assertEqual(len(service.score_every_class.calls), 1)  # type: ignore[attr-defined]
        self.assertEqual(service.perform_game_action.executed, [])
        service.score_every_class.release.set()  # type: ignore[attr-defined]

    async def test_returns_none_when_the_model_raises(self):
        service = make_fast_command_service(model_error=RuntimeError("boom"))

        with self.assertLogs(instinct_service.logger, level="ERROR"):
            reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(len(service.score_every_class.calls), 1)  # type: ignore[attr-defined]
        self.assertEqual(service.perform_game_action.executed, [])

    async def test_replies_at_once_when_the_game_window_is_not_found(self):
        tool = FakePerformGameAction(
            result=ToolReturn(
                return_value="Game window not found, nothing was pressed.",
                metadata={"is_error": True},
            )
        )
        service = make_fast_command_service(perform_game_action=tool)

        reply = await service.try_fast_command("deploy landing gear")

        self.assertEqual(
            reply, FastCommandReply("Game window not found, nothing was pressed.")
        )
        self.assertEqual(len(service.score_every_class.calls), 1)  # type: ignore[attr-defined]
        self.assertEqual(tool.executed, [EdAction.LANDING_GEAR_TOGGLE])

    async def test_replies_with_the_reason_when_the_tool_says_unavailable(self):
        tool = FakePerformGameAction(
            result=ToolReturn(
                return_value="Landing gear unavailable: the ship is in supercruise.",
                metadata={"is_error": False, "unavailable": True},
            )
        )
        service = make_fast_command_service(perform_game_action=tool)

        reply = await service.try_fast_command("deploy landing gear")

        # The reason stays for the log and the LLM, the pilot hears the clip. The
        # gear is an action of the game state, but nothing changes in the game, so
        # the refusal is spoken here
        self.assertEqual(reply, FastCommandReply("Landing gear unavailable"))
        self.assertTrue(reply.is_spoken)  # type: ignore[attr-defined]
        self.assertEqual(tool.executed, [EdAction.LANDING_GEAR_TOGGLE])

    async def test_replies_game_actions_disabled_for_a_command_when_they_are_off(
        self,
    ):
        service = make_fast_command_service(game_actions_enabled=False)

        with self.assertLogs(instinct_service.logger, level="INFO") as logs:
            reply = await service.try_fast_command("deploy landing gear")

        self.assertEqual(reply, FastCommandReply("Game actions disabled"))
        self.assertIn(reply.text, REPLY_TEXTS)  # type: ignore[attr-defined]
        self.assertEqual(len(service.score_every_class.calls), 1)  # type: ignore[attr-defined]
        self.assertEqual(service.perform_game_action.executed, [])
        fast_command_lines = [line for line in logs.output if "Fast command" in line]
        self.assertEqual(len(fast_command_lines), 1)
        self.assertIn("LandingGearToggle was not done", fast_command_lines[0])

    async def test_sends_talk_to_the_llm_when_game_actions_are_off(self):
        service = make_fast_command_service(choice="none", game_actions_enabled=False)

        reply = await service.try_fast_command("how much fuel do I have")

        self.assertIsNone(reply)
        self.assertEqual(len(service.score_every_class.calls), 1)  # type: ignore[attr-defined]
        self.assertEqual(service.perform_game_action.executed, [])

    async def test_does_not_ask_the_model_when_the_module_is_off_whatever_the_actions(
        self,
    ):
        service = make_fast_command_service(enabled=False, game_actions_enabled=False)

        reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(service.score_every_class.calls, [])  # type: ignore[attr-defined]

    async def test_names_a_toggle_after_the_direction_it_went(self):
        service = make_fast_command_service(
            choice="LandingGearToggle",
            ship=make_ship_stats(is_landing_gear_down=True),
        )

        reply = await service.try_fast_command("raise the landing gear")

        self.assertEqual(reply, FastCommandReply("Landing gear retracted", False))

    async def test_reads_the_ship_before_the_key_is_pressed(self):
        service = make_fast_command_service(choice="LandingGearToggle")
        real_perform_game_action = service.perform_game_action.perform_game_action

        async def press_and_lower_the_gear(action):
            # The key changes the ship: the gear is down when the tool returns
            service.game_state_protocol.ship = make_ship_stats(  # type: ignore[attr-defined]
                is_landing_gear_down=True
            )
            return await real_perform_game_action(action)

        service.perform_game_action.perform_game_action = press_and_lower_the_gear  # type: ignore[method-assign]

        reply = await service.try_fast_command("deploy landing gear")

        self.assertEqual(reply, FastCommandReply("Landing gear deployed", False))

    async def test_does_not_speak_the_reply_of_an_action_the_game_state_says(self):
        for action in ACTIONS_SAID_BY_GAME_STATE:
            with self.subTest(action=action.value):
                service = make_fast_command_service(choice=action.value)

                reply = await service.try_fast_command("do it")

                assert reply is not None
                self.assertFalse(reply.is_spoken)
                self.assertTrue(reply.text)  # still written to COMMS

    async def test_speaks_the_reply_of_an_action_with_no_trace_in_the_game_state(self):
        for action, text in [
            (EdAction.SET_SPEED_ZERO, "Throttle zero"),
            (EdAction.USE_BOOST_JUICE, "Boosting"),
            (EdAction.CYCLE_NEXT_TARGET, "Next target"),
        ]:
            with self.subTest(action=action.value):
                service = make_fast_command_service(choice=action.value)

                reply = await service.try_fast_command("do it")

                self.assertEqual(reply, FastCommandReply(text))

    async def test_logs_that_the_action_was_not_done_when_the_tool_refuses(self):
        tool = FakePerformGameAction(
            result=ToolReturn(
                return_value="Landing gear unavailable: the ship is docked.",
                metadata={"is_error": False, "unavailable": True},
            )
        )
        service = make_fast_command_service(perform_game_action=tool)

        with self.assertLogs(instinct_service.logger, level="INFO") as logs:
            await service.try_fast_command("deploy landing gear")

        fast_command_lines = [line for line in logs.output if "Fast command" in line]
        self.assertEqual(len(fast_command_lines), 1)
        line = fast_command_lines[0]
        self.assertIn("'deploy landing gear'", line)
        self.assertIn("LandingGearToggle was not done", line)
        self.assertIn("Landing gear unavailable: the ship is docked.", line)
        self.assertNotIn("Instinct pressed", line)

    async def test_returns_none_when_the_tool_raises(self):
        tool = FakePerformGameAction(error=RuntimeError("boom"))
        service = make_fast_command_service(perform_game_action=tool)

        with self.assertLogs(instinct_service.logger, level="ERROR"):
            reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(tool.executed, [EdAction.LANDING_GEAR_TOGGLE])

    async def test_one_model_call_runs_at_a_time(self):
        service = make_fast_command_service()
        service.score_every_class.seconds_per_call = 0.1  # type: ignore[attr-defined]
        offered = [EdAction.SUPERCRUISE]

        await asyncio.gather(
            asyncio.to_thread(
                service.pick_offered_action, "engage supercruise", offered
            ),
            asyncio.to_thread(
                service.pick_offered_action, "engage supercruise", offered
            ),
        )

        self.assertEqual(len(service.score_every_class.calls), 2)  # type: ignore[attr-defined]
        self.assertEqual(service.score_every_class.most_running_at_once, 1)  # type: ignore[attr-defined]
