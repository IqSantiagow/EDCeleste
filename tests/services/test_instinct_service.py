import asyncio
import unittest
from unittest.mock import MagicMock, Mock

import httpx

from edceleste.services.decision_model_download_service import DownloadCancelled
from edceleste.services.instinct_service import InstinctService
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
        self.model_service = MagicMock()
        self.model_service.running_device.return_value = None
        return InstinctService(
            self.settings_service, download_service, self.model_service
        )

    async def wait_for_background_work(self, service: InstinctService) -> None:
        if service.background_task:
            await service.background_task

    async def test_disabled_instinct_unloads_the_model_and_downloads_nothing(self):
        download_service = FakeDownloadService()
        service = self.make_service(enabled=False, download_service=download_service)

        service.reload_service()

        self.model_service.unload_model.assert_called_once_with()
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

        self.model_service.change_device.assert_called_once_with("cpu")

    async def test_enabled_instinct_downloads_a_missing_model_and_loads_it(self):
        download_service = FakeDownloadService()
        service = self.make_service(enabled=True, download_service=download_service)

        service.reload_service()
        await self.wait_for_background_work(service)

        self.assertTrue(download_service.downloaded)
        self.model_service.warm_up.assert_called_once_with()
        self.assertEqual(service.get_model_state(), InstinctModelState.READY)

    async def test_enabled_instinct_with_a_downloaded_model_only_loads_it(self):
        service = self.make_service(
            enabled=True, download_service=FakeDownloadService(downloaded=True)
        )

        service.reload_service()
        await self.wait_for_background_work(service)

        self.model_service.warm_up.assert_called_once_with()

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
        self.model_service.warm_up.assert_not_called()

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
        self.model_service.warm_up.side_effect = RuntimeError("CUDA out of memory")

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
        download_service.get_download_size = Mock(side_effect=OSError("offline"))
        service = self.make_service(enabled=True, download_service=download_service)

        self.assertIsNone(service.get_download_size())

    async def test_download_size_is_asked_from_the_hub_only_once(self):
        download_service = FakeDownloadService()
        download_service.get_download_size = Mock(return_value=MODEL_BYTES)
        service = self.make_service(enabled=True, download_service=download_service)

        service.get_download_size()
        size = service.get_download_size()

        self.assertEqual(size, MODEL_BYTES)
        download_service.get_download_size.assert_called_once_with()


class InstinctColdStartTest(unittest.IsolatedAsyncioTestCase):
    def make_service(self, enabled: bool, download_service: FakeDownloadService):
        settings_service = Mock()
        settings_service.get_settings.return_value = make_settings(enabled)
        self.model_service = MagicMock()
        return InstinctService(settings_service, download_service, self.model_service)

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
