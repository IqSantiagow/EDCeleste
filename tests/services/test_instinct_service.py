import asyncio
import functools
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import httpx

from edceleste.services import instinct_service
from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
    DownloadCancelled,
)
from edceleste.services.instinct_service import (
    InstinctService,
    ModelNotDownloaded,
    switch_qwen_kernels_to_device,
)
from edceleste.services.models.instinct_status import (
    DownloadProgress,
    InstinctFailure,
    InstinctModelState,
)
from edceleste.services.models.settings_model import (
    InstinctModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)

MODEL_BYTES = 1_500_000_000
MODULE = "edceleste.services.instinct_service"


def make_settings(enabled: bool, device: str = "auto") -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(volume=1.0),
        llm=LLMModel(
            system_prompt="sp",
            user_prompt="",
            instinct=InstinctModel(enabled=enabled, device=device),
        ),
        stt=SttModel(model="tiny.en"),
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


class InstinctServiceTest(unittest.IsolatedAsyncioTestCase):
    def make_service(self, enabled: bool, download_service: FakeDownloadService):
        self.settings_service = Mock()
        self.settings_service.get_settings.return_value = make_settings(enabled)
        service = InstinctService(self.settings_service, download_service)
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
        service = InstinctService(settings_service, download_service)
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


class InstinctModelLoadingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.download_service = MagicMock(spec=DecisionModelDownloadService)
        self.download_service.model_folder = Path("C:/models/decider")
        self.download_service.is_model_downloaded.return_value = True
        self.service = InstinctService(Mock(), self.download_service)

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

    def test_warm_up_asks_one_question_so_the_first_command_is_fast(self):
        self.service.ask_decision_model = MagicMock(
            return_value={"warm_up": {"noul": 0.9}}
        )

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
