import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from edceleste.services.decision_model_download_service import (
    DOWNLOAD_COMPLETE_FILE,
    DecisionModelDownloadService,
    DownloadCancelled,
    find_models_directory,
)

MODULE = "edceleste.services.decision_model_download_service"
FILES_ON_HUB = {
    "config.json": b'{"model_type": "qwen3_5"}',
    "model.safetensors": bytes(range(256)) * 20_000,  # 5 MB, several chunks
}
REAL_ASYNC_CLIENT = httpx.AsyncClient


class FakeHubServer:
    def __init__(self, broken: bool = False) -> None:
        self.broken = broken

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.broken:
            raise httpx.ConnectError("network is down", request=request)
        return httpx.Response(
            200, content=FILES_ON_HUB[request.url.path.split("/")[-1]]
        )

    def client(self, **kwargs) -> httpx.AsyncClient:
        return REAL_ASYNC_CLIENT(transport=httpx.MockTransport(self.handle), **kwargs)


class DecisionModelDownloadServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.service = DecisionModelDownloadService(Path(temporary_directory.name))

        files_patcher = patch(
            f"{MODULE}.fetch_file_sizes_by_name_from_hub",
            return_value={name: len(content) for name, content in FILES_ON_HUB.items()},
        )
        files_patcher.start()
        self.addCleanup(files_patcher.stop)
        url_patcher = patch(
            f"{MODULE}.build_file_url_on_hub",
            side_effect=lambda name: f"https://hub.test/{name}",
        )
        url_patcher.start()
        self.addCleanup(url_patcher.stop)

        self.use_hub(FakeHubServer())

    def use_hub(self, hub: FakeHubServer) -> None:
        client_patcher = patch(f"{MODULE}.httpx.AsyncClient", side_effect=hub.client)
        client_patcher.start()
        self.addCleanup(client_patcher.stop)

    async def download_everything(self) -> list:
        return [progress async for progress in self.service.download_model()]

    def test_model_is_not_downloaded_at_first(self):
        self.assertFalse(self.service.is_model_downloaded())

    def test_download_size_is_the_sum_of_files_on_hub(self):
        self.assertEqual(
            self.service.get_download_size(),
            sum(len(content) for content in FILES_ON_HUB.values()),
        )

    async def test_download_puts_every_file_on_disk(self):
        await self.download_everything()

        for name, content in FILES_ON_HUB.items():
            self.assertEqual((self.service.model_folder / name).read_bytes(), content)
        self.assertTrue(self.service.is_model_downloaded())

    async def test_download_progress_grows_up_to_the_total(self):
        progress_list = await self.download_everything()

        bytes_done = [progress.bytes_done for progress in progress_list]
        total = sum(len(content) for content in FILES_ON_HUB.values())
        self.assertEqual(bytes_done, sorted(bytes_done))
        self.assertEqual(progress_list[-1].bytes_done, total)
        self.assertEqual(progress_list[-1].bytes_total, total)

    async def cancel_after_the_first_megabyte(self) -> None:
        with self.assertRaises(DownloadCancelled):
            async for progress in self.service.download_model():
                if progress.bytes_done > 1_000_000:
                    self.service.cancel_download()

    async def test_cancel_removes_what_was_downloaded(self):
        await self.cancel_after_the_first_megabyte()

        self.assertFalse(self.service.is_model_downloaded())
        self.assertFalse(self.service.model_folder.exists())

    async def test_download_after_cancel_starts_over_and_completes(self):
        await self.cancel_after_the_first_megabyte()

        await self.download_everything()

        self.assertEqual(
            (self.service.model_folder / "model.safetensors").read_bytes(),
            FILES_ON_HUB["model.safetensors"],
        )
        self.assertTrue(self.service.is_model_downloaded())

    async def test_network_failure_raises_and_removes_what_was_downloaded(self):
        self.use_hub(FakeHubServer(broken=True))

        with self.assertRaises(httpx.ConnectError):
            await self.download_everything()

        self.assertFalse(self.service.is_model_downloaded())
        self.assertFalse(self.service.model_folder.exists())

    async def test_complete_marker_is_written_only_at_the_end(self):
        async for progress in self.service.download_model():
            if progress.bytes_done < progress.bytes_total:
                self.assertFalse(
                    (self.service.model_folder / DOWNLOAD_COMPLETE_FILE).exists()
                )

        self.assertTrue((self.service.model_folder / DOWNLOAD_COMPLETE_FILE).exists())


class FindModelsDirectoryTest(unittest.TestCase):
    def test_windows_uses_local_app_data(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": "C:/Users/pilot/AppData/Local"}):
            folder = find_models_directory("nt")

        self.assertEqual(
            folder, Path("C:/Users/pilot/AppData/Local") / "EDCeleste" / "models"
        )

    def test_linux_uses_local_share(self):
        folder = find_models_directory("posix")

        self.assertEqual(
            folder, Path.home() / ".local" / "share" / "EDCeleste" / "models"
        )
