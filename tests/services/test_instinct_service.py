import asyncio
import functools
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import httpx
from pydantic_ai import ToolReturn

from edceleste.services import instinct_service
from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
    DownloadCancelled,
)
from edceleste.services.instinct_service import (
    InstinctService,
    ModelNotDownloaded,
    describe_top_scores,
    switch_qwen_kernels_to_device,
)
from edceleste.services.models.instinct_actions import build_which_action_questions
from edceleste.services.models.instinct_status import (
    DownloadProgress,
    InstinctFailure,
    InstinctModelState,
)
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.settings_model import (
    GameActionsModel,
    InstinctModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)

MODEL_BYTES = 1_500_000_000
MODULE = "edceleste.services.instinct_service"


def make_settings(
    enabled: bool, device: str = "auto", game_actions_enabled: bool = False
) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(volume=1.0),
        llm=LLMModel(
            system_prompt="sp",
            user_prompt="",
            instinct=InstinctModel(enabled=enabled, device=device),
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

    async def execute(self, action: EdAction) -> ToolReturn:
        self.executed.append(action)
        if self.error is not None:
            raise self.error
        return self.result


class FakeGameState:
    def __init__(self, text: str = "Commander name is NOVA."):
        self.text = text

    def get_game_state_projection(self) -> str:
        return self.text


class FakeDecider:
    """Stands for decider.infer.Decider. Answers the "action" question with a
    fixed choice and records every call, also how many ran at the same time."""

    def __init__(
        self,
        choice: str = "none",
        device: str = "cuda",
        error: Exception | None = None,
    ):
        self.dev = device
        self.choice = choice
        self.error = error
        self.seconds_per_call = 0.0
        # The size of the input the model reports, None when it reports nothing
        self.input_tokens: int | None = None
        self.release = threading.Event()  # clear it to keep the model busy
        self.release.set()
        self.calls: list[tuple[dict, dict]] = []
        self.running_now = 0
        self.most_running_at_once = 0
        self.counter_lock = threading.Lock()

    def system_one(self, state: dict, questions: dict) -> dict:
        with self.counter_lock:
            self.calls.append((state, questions))
            self.running_now += 1
            self.most_running_at_once = max(self.most_running_at_once, self.running_now)
        try:
            self.release.wait(5)
            time.sleep(self.seconds_per_call)
            if self.error is not None:
                raise self.error
            probabilities = {name: 0.01 for name in questions["action"]["criteria"]}
            probabilities[self.choice] = 0.9
            answer = {"choice": self.choice, "probabilities": probabilities}
            result: dict = {"answers": {"action": answer}}
            if self.input_tokens is not None:
                result["usage"] = {"input_tokens": self.input_tokens}
            return result
        finally:
            with self.counter_lock:
                self.running_now -= 1


def make_fast_command_service(
    enabled: bool = True,
    device: str = "cuda",
    game_actions_enabled: bool = True,
    choice: str = "LandingGearToggle",
    keybinds: FakeKeybinds | None = None,
    game_state_text: str = "Commander name is NOVA.",
    decider_error: Exception | None = None,
    perform_game_action: FakePerformGameAction | None = None,
) -> InstinctService:
    """A service that is ready to decide: on, loaded on the GPU, game actions on,
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
        FakeGameState(game_state_text),
        perform_game_action or FakePerformGameAction(),  # type: ignore[arg-type]
    )
    service.enabled = enabled
    service.decider = FakeDecider(choice=choice, device=device, error=decider_error)  # type: ignore[assignment]
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
        service.decider = MagicMock()

        with patch.dict(sys.modules, {"torch": MagicMock()}):
            service.reload_service()

        self.assertIsNone(service.decider)
        self.assertIsNone(service.background_task)
        self.assertEqual(service.get_model_state(), InstinctModelState.NOT_DOWNLOADED)

    async def test_reload_passes_the_chosen_device_to_the_model(self):
        service = self.make_service(
            enabled=False, download_service=FakeDownloadService()
        )
        self.settings_service.get_settings.return_value = make_settings(
            enabled=False, device="cpu"
        )

        service.reload_service()

        self.assertEqual(service.device_choice, "cpu")

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
        service.warm_up.side_effect = RuntimeError("CUDA out of memory")

        service.reload_service()
        await self.wait_for_background_work(service)

        self.assertEqual(
            service.get_status().failure, InstinctFailure("load", "CUDA out of memory")
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

    async def test_model_on_the_cpu_is_a_warning_that_commands_go_through_celeste(self):
        service = self.make_service(True, FakeDownloadService(downloaded=True))
        service.decider = FakeDecider(device="cpu")  # type: ignore[assignment]

        statuses = [status async for status in service.cold_start()]

        self.assertTrue(statuses[-1].completed)
        self.assertTrue(statuses[-1].is_warning)
        self.assertFalse(statuses[-1].is_critical)
        self.assertEqual(
            statuses[-1].message,
            "model runs on the CPU, too slow for commands. "
            "Commands go through Celeste.",
        )

    async def test_model_on_the_gpu_gives_no_warning(self):
        service = self.make_service(True, FakeDownloadService(downloaded=True))
        service.decider = FakeDecider(device="cuda")  # type: ignore[assignment]

        statuses = [status async for status in service.cold_start()]

        self.assertTrue(statuses[-1].completed)
        self.assertFalse(statuses[-1].is_warning)
        self.assertIsNone(statuses[-1].message)


class InstinctModelLoadingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.download_service = MagicMock(spec=DecisionModelDownloadService)
        self.download_service.model_folder = Path("C:/models/decider")
        self.download_service.is_model_downloaded.return_value = True
        self.service = InstinctService(
            Mock(), self.download_service, Mock(), Mock(), Mock()
        )

    def load_with_fake_decider(self, cuda_available: bool = True, triton=True):
        fake_decider_module = MagicMock()
        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = cuda_available
        with (
            patch.dict(
                sys.modules,
                {
                    "torch": fake_torch,
                    "decider": MagicMock(),
                    "decider.infer": fake_decider_module,
                },
            ),
            patch(f"{MODULE}.switch_qwen_kernels_to_device") as switch_kernels_mock,
            patch(
                f"{MODULE}.importlib.util.find_spec",
                return_value=MagicMock() if triton else None,
            ),
        ):
            self.service.load_model()
        return fake_decider_module.Decider, switch_kernels_mock

    def test_load_model_reads_the_downloaded_folder_on_the_gpu(self):
        decider_class, switch_kernels_mock = self.load_with_fake_decider()

        decider_class.assert_called_once_with(
            str(self.download_service.model_folder), device="cuda"
        )
        switch_kernels_mock.assert_called_once_with("cuda")

    def test_load_model_auto_falls_back_to_cpu_without_a_gpu(self):
        decider_class, _ = self.load_with_fake_decider(cuda_available=False)

        self.assertEqual(decider_class.call_args.kwargs["device"], "cpu")

    def test_load_model_uses_the_chosen_device(self):
        self.service.change_device("cpu")

        decider_class, switch_kernels_mock = self.load_with_fake_decider()

        self.assertEqual(decider_class.call_args.kwargs["device"], "cpu")
        switch_kernels_mock.assert_called_once_with("cpu")

    def test_load_model_runs_eager_forward_without_triton(self):
        decider_class, _ = self.load_with_fake_decider(triton=False)

        engine = decider_class.return_value.eng
        self.assertIs(engine._fwd_impl, engine._fwd_eager)

    def test_load_model_refuses_a_model_that_is_not_downloaded(self):
        self.download_service.is_model_downloaded.return_value = False

        with self.assertRaises(ModelNotDownloaded):
            self.service.load_model()

    def test_change_device_unloads_the_model(self):
        self.service.decider = MagicMock()

        with patch.dict(sys.modules, {"torch": MagicMock()}):
            self.service.change_device("cpu")

        self.assertIsNone(self.service.decider)

    def test_running_device_is_none_before_loading(self):
        self.assertIsNone(self.service.running_device())

    def test_running_device_reports_where_the_model_runs(self):
        self.service.decider = MagicMock(dev="cuda")

        self.assertEqual(self.service.running_device(), "cuda")

    def test_warm_up_asks_only_the_small_question_when_there_is_no_game_state(self):
        self.service.ask_decision_model = MagicMock(
            return_value={"warm_up": {"noul": 0.9}}
        )
        self.service.game_state_protocol.get_game_state_projection.return_value = ""

        self.service.warm_up()

        self.service.ask_decision_model.assert_called_once()

    def test_unload_model_frees_the_model(self):
        self.service.decider = MagicMock()

        with patch.dict(sys.modules, {"torch": MagicMock()}):
            self.service.unload_model()

        self.assertIsNone(self.service.decider)


class SwitchQwenKernelsToDeviceTest(unittest.TestCase):
    def setUp(self):
        def torch_chunk_gated_delta_rule():
            return "torch"

        @functools.wraps(torch_chunk_gated_delta_rule)
        def fast_chunk_gated_delta_rule():
            return "gpu"

        def torch_recurrent_gated_delta_rule():
            return "torch"

        @functools.wraps(torch_recurrent_gated_delta_rule)
        def fast_recurrent_gated_delta_rule():
            return "gpu"

        self.qwen_module = SimpleNamespace(
            torch_chunk_gated_delta_rule=fast_chunk_gated_delta_rule,
            torch_recurrent_gated_delta_rule=fast_recurrent_gated_delta_rule,
        )
        modules_patcher = patch.dict(
            sys.modules,
            {
                "transformers.models.qwen3_5": SimpleNamespace(
                    modeling_qwen3_5=self.qwen_module
                ),
            },
        )
        modules_patcher.start()
        self.addCleanup(modules_patcher.stop)
        kernels_patcher = patch.dict(instinct_service.gpu_kernels, clear=True)
        kernels_patcher.start()
        self.addCleanup(kernels_patcher.stop)

    def test_cpu_gets_the_plain_torch_functions(self):
        switch_qwen_kernels_to_device("cpu")

        self.assertEqual(self.qwen_module.torch_chunk_gated_delta_rule(), "torch")
        self.assertEqual(self.qwen_module.torch_recurrent_gated_delta_rule(), "torch")

    def test_cuda_gets_the_gpu_kernels_back_after_cpu(self):
        switch_qwen_kernels_to_device("cpu")

        switch_qwen_kernels_to_device("cuda")

        self.assertEqual(self.qwen_module.torch_chunk_gated_delta_rule(), "gpu")
        self.assertEqual(self.qwen_module.torch_recurrent_gated_delta_rule(), "gpu")


class CanDecideCommandsTest(unittest.TestCase):
    # Every test starts from a service that can decide and breaks one condition

    def test_is_true_when_on_loaded_on_the_gpu_and_game_actions_are_on(self):
        service = make_fast_command_service()

        self.assertTrue(service.can_decide_commands())

    def test_is_false_when_instinct_is_disabled(self):
        service = make_fast_command_service(enabled=False)

        self.assertFalse(service.can_decide_commands())

    def test_is_false_when_the_model_runs_on_the_cpu(self):
        service = make_fast_command_service(device="cpu")

        self.assertFalse(service.can_decide_commands())

    def test_is_false_when_the_model_is_not_loaded(self):
        service = make_fast_command_service()
        service.decider = None

        self.assertFalse(service.can_decide_commands())

    def test_is_false_when_game_actions_are_off(self):
        service = make_fast_command_service(game_actions_enabled=False)

        self.assertFalse(service.can_decide_commands())


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
    def test_sends_the_state_and_the_question_to_the_model_and_returns_its_answer(self):
        service = make_fast_command_service(choice="Supercruise")
        offered = [EdAction.SUPERCRUISE, EdAction.LANDING_GEAR_TOGGLE]

        answer = service.ask_which_action("State text", "engage supercruise", offered)

        self.assertEqual(answer["choice"], "Supercruise")
        self.assertEqual(
            service.decider.calls,  # type: ignore[union-attr]
            [
                (
                    {"game_state": "State text", "pilot_said": "engage supercruise"},
                    build_which_action_questions(offered),
                )
            ],
        )


class AskDecisionModelInputSizeTest(unittest.TestCase):
    def ask_the_model(self, service: InstinctService) -> None:
        questions = build_which_action_questions([EdAction.SUPERCRUISE])
        service.ask_decision_model(
            {"game_state": "State", "pilot_said": "go"}, questions
        )

    def test_remembers_the_input_size_the_model_reported(self):
        service = make_fast_command_service()
        service.decider.input_tokens = 321  # type: ignore[union-attr]

        self.ask_the_model(service)

        self.assertEqual(service.last_input_tokens, 321)

    def test_forgets_the_old_input_size_when_the_model_reports_none(self):
        service = make_fast_command_service()
        service.last_input_tokens = 99  # from a decision before

        self.ask_the_model(service)  # this answer has no "usage"

        self.assertEqual(service.last_input_tokens, 0)


class WarmUpTest(unittest.TestCase):
    def make_service(
        self, game_state_text: str = "State text", keybinds: FakeKeybinds | None = None
    ) -> InstinctService:
        """A service that is ready to decide, whose three questions of the warm
        up are replaced, so only the order of the warm up is tested."""
        service = make_fast_command_service(
            game_state_text=game_state_text, keybinds=keybinds
        )
        service.ask_decision_model = MagicMock(return_value={})  # type: ignore[method-assign]
        service.ask_which_action = MagicMock()  # type: ignore[method-assign]
        service.compile_engine_for_input_sizes_near = MagicMock()  # type: ignore[method-assign]
        return service

    def test_asks_the_real_command_question_with_the_game_state_and_the_keys(self):
        service = self.make_service()

        service.warm_up()

        service.ask_which_action.assert_called_once_with(  # type: ignore[attr-defined]
            "State text", "deploy hardpoints", service.find_actions_with_a_key()
        )

    def test_skips_the_command_question_when_no_action_has_a_key(self):
        service = self.make_service(keybinds=FakeKeybinds(bound_actions=set()))

        service.warm_up()

        service.ask_decision_model.assert_called_once()  # type: ignore[attr-defined]
        service.ask_which_action.assert_not_called()  # type: ignore[attr-defined]
        service.compile_engine_for_input_sizes_near.assert_not_called()  # type: ignore[attr-defined]

    def test_skips_the_command_question_when_there_is_no_game_state(self):
        service = self.make_service(game_state_text="")

        service.warm_up()

        service.ask_decision_model.assert_called_once()  # type: ignore[attr-defined]
        service.ask_which_action.assert_not_called()  # type: ignore[attr-defined]
        service.compile_engine_for_input_sizes_near.assert_not_called()  # type: ignore[attr-defined]

    def test_compiles_the_input_sizes_near_what_the_command_needed(self):
        service = self.make_service()

        def ask_which_action(game_state, pilot_message, offered_actions):
            service.last_input_tokens = 321  # what the real question reports

        service.ask_which_action.side_effect = ask_which_action  # type: ignore[attr-defined]

        service.warm_up()

        service.compile_engine_for_input_sizes_near.assert_called_once_with(321)  # type: ignore[attr-defined]


class CompileEngineForInputSizesNearTest(unittest.TestCase):
    SIZES = [64, 128, 192, 256, 320, 384, 512]

    def setUp(self):
        modules_patcher = patch.dict(
            sys.modules,
            {
                "decider": MagicMock(),
                "decider.engine": SimpleNamespace(T_BUCKETS=self.SIZES),
            },
        )
        modules_patcher.start()
        self.addCleanup(modules_patcher.stop)

        self.engine = Mock()
        self.service = make_fast_command_service()
        self.service.decider = SimpleNamespace(eng=self.engine)  # type: ignore[assignment]

    def compiled_shapes(self) -> list[tuple[int, int]]:
        """The (batch, size) shapes the engine was asked to compile."""
        return [
            shape
            for engine_call in self.engine.warmup.call_args_list
            for shape in engine_call.args[0]
        ]

    def test_compiles_the_size_of_the_command_and_the_sizes_next_to_it(self):
        self.service.compile_engine_for_input_sizes_near(
            300
        )  # 320 is the smallest that holds it

        self.assertEqual(self.compiled_shapes(), [(1, 256), (1, 320), (1, 384)])

    def test_the_smallest_size_has_no_size_below_it(self):
        self.service.compile_engine_for_input_sizes_near(10)

        self.assertEqual(self.compiled_shapes(), [(1, 64), (1, 128)])

    def test_the_largest_size_has_no_size_above_it(self):
        self.service.compile_engine_for_input_sizes_near(500)

        self.assertEqual(self.compiled_shapes(), [(1, 384), (1, 512)])

    def test_an_input_that_fits_a_size_exactly_uses_that_size(self):
        self.service.compile_engine_for_input_sizes_near(320)

        self.assertEqual(self.compiled_shapes(), [(1, 256), (1, 320), (1, 384)])

    def test_compiles_nothing_when_the_input_is_bigger_than_every_size(self):
        self.service.compile_engine_for_input_sizes_near(600)

        self.engine.warmup.assert_not_called()

    def test_compiles_nothing_when_the_model_did_not_tell_its_input_size(self):
        self.service.compile_engine_for_input_sizes_near(0)

        self.engine.warmup.assert_not_called()

    def test_does_not_fail_without_the_engine_of_the_model(self):
        self.service.decider = FakeDecider(device="cpu")  # type: ignore[assignment]

        self.service.compile_engine_for_input_sizes_near(300)

    def test_holds_the_model_lock_while_compiling(self):
        locked_while_compiling: list[bool] = []
        self.engine.warmup.side_effect = lambda shapes: locked_while_compiling.append(
            self.service.model_lock.locked()
        )

        self.service.compile_engine_for_input_sizes_near(300)

        self.assertEqual(locked_while_compiling, [True])
        self.assertFalse(self.service.model_lock.locked())


class DescribeTopScoresTest(unittest.TestCase):
    def test_lists_the_best_three_options_best_first(self):
        scores = {"a": 0.10, "b": 0.70, "c": 0.15, "d": 0.05}

        self.assertEqual(describe_top_scores(scores), "b 0.70, c 0.15, a 0.10")


class TryFastCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_gives_the_chosen_action_to_the_tool_and_returns_the_reply(self):
        service = make_fast_command_service(choice="LandingGearToggle")

        reply = await service.try_fast_command("deploy landing gear")

        self.assertEqual(reply, "Done: Landing gear toggle")
        self.assertEqual(
            service.perform_game_action.executed, [EdAction.LANDING_GEAR_TOGGLE]
        )
        self.assertEqual(
            service.decider.calls[0][0],  # type: ignore[union-attr]
            {
                "game_state": "Commander name is NOVA.",
                "pilot_said": "deploy landing gear",
            },
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
        self.assertEqual(len(service.decider.calls), 1)  # type: ignore[union-attr]
        self.assertEqual(service.perform_game_action.executed, [])

    async def test_does_not_ask_the_model_when_it_cannot_decide(self):
        service = make_fast_command_service(enabled=False)

        reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(service.decider.calls, [])  # type: ignore[union-attr]

    async def test_does_not_ask_the_model_when_no_action_has_a_key(self):
        service = make_fast_command_service(keybinds=FakeKeybinds(bound_actions=set()))

        reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(service.decider.calls, [])  # type: ignore[union-attr]

    async def test_does_not_ask_the_model_when_the_game_state_is_empty(self):
        service = make_fast_command_service(game_state_text="")

        reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(service.decider.calls, [])  # type: ignore[union-attr]

    async def test_returns_none_when_the_model_runs_out_of_time(self):
        service = make_fast_command_service(choice="LandingGearToggle")
        service.decider.release.clear()  # type: ignore[union-attr]

        with (
            patch.object(instinct_service, "FAST_COMMAND_TIMEOUT_SECONDS", 0.2),
            self.assertLogs(instinct_service.logger, level="WARNING"),
        ):
            reply = await service.try_fast_command("deploy landing gear")

        # Checked before the model is let go: its late answer would press the key
        self.assertIsNone(reply)
        self.assertEqual(len(service.decider.calls), 1)  # type: ignore[union-attr]
        self.assertEqual(service.perform_game_action.executed, [])
        service.decider.release.set()  # type: ignore[union-attr]

    async def test_returns_none_when_the_model_raises(self):
        service = make_fast_command_service(decider_error=RuntimeError("boom"))

        with self.assertLogs(instinct_service.logger, level="ERROR"):
            reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(len(service.decider.calls), 1)  # type: ignore[union-attr]
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

        self.assertEqual(reply, "Game window not found, nothing was pressed.")
        self.assertEqual(len(service.decider.calls), 1)  # type: ignore[union-attr]
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

        self.assertEqual(reply, "Landing gear unavailable: the ship is in supercruise.")
        self.assertEqual(tool.executed, [EdAction.LANDING_GEAR_TOGGLE])

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

    async def test_returns_none_when_the_model_answers_an_unknown_action(self):
        service = make_fast_command_service(choice="NotARealAction")

        with self.assertLogs(instinct_service.logger, level="ERROR"):
            reply = await service.try_fast_command("deploy landing gear")

        self.assertIsNone(reply)
        self.assertEqual(len(service.decider.calls), 1)  # type: ignore[union-attr]
        self.assertEqual(service.perform_game_action.executed, [])

    async def test_one_model_call_runs_at_a_time(self):
        service = make_fast_command_service()
        service.decider.seconds_per_call = 0.1  # type: ignore[union-attr]
        state = {"game_state": "state", "pilot_said": "engage supercruise"}
        questions = build_which_action_questions([EdAction.SUPERCRUISE])

        await asyncio.gather(
            asyncio.to_thread(service.ask_decision_model, state, questions),
            asyncio.to_thread(service.ask_decision_model, state, questions),
        )

        self.assertEqual(len(service.decider.calls), 2)  # type: ignore[union-attr]
        self.assertEqual(service.decider.most_running_at_once, 1)  # type: ignore[union-attr]
