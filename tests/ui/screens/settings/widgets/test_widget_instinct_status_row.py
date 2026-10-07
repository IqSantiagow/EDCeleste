import unittest

from textual.app import App, ComposeResult
from textual.widgets import Label

from edceleste.services.models.instinct_status import (
    DownloadProgress,
    InstinctFailure,
    InstinctModelState,
    InstinctStatus,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.screens.settings.widgets.system_prompts.widget_instinct_status_row import (  # noqa: E501
    WidgetInstinctStatusRow,
)

MODEL_BYTES = 1_500_000_000


class FakeSettingsRepository:
    def __init__(self, status: InstinctStatus, download_size: int | None) -> None:
        self.status = status
        self.download_size = download_size
        self.download_calls = 0
        self.cancel_calls = 0

    def get_instinct_status(self) -> InstinctStatus:
        return self.status

    async def get_instinct_download_size(self) -> int | None:
        return self.download_size

    def download_instinct_model(self) -> None:
        self.download_calls += 1

    def cancel_instinct_download(self) -> None:
        self.cancel_calls += 1


def make_status(
    state: InstinctModelState,
    download_progress: DownloadProgress | None = None,
    running_device: str | None = None,
    failure: InstinctFailure | None = None,
) -> InstinctStatus:
    return InstinctStatus(state, download_progress, running_device, failure)


class RowTestApp(App):
    def __init__(self, repository: FakeSettingsRepository) -> None:
        super().__init__()
        self.repository = repository

    def compose(self) -> ComposeResult:
        yield WidgetInstinctStatusRow(self.repository)  # type: ignore[arg-type]


def status_text(app: App) -> str:
    return str(app.query_one("#instinct-status-text", Label).content)


def button(app: App) -> WidgetButton:
    return app.query_one("#instinct-status-button", WidgetButton)


class TestWidgetInstinctStatusRow(unittest.IsolatedAsyncioTestCase):
    async def test_not_downloaded_shows_the_size_from_the_hub_and_download(self):
        repository = FakeSettingsRepository(
            make_status(InstinctModelState.NOT_DOWNLOADED), MODEL_BYTES
        )
        app = RowTestApp(repository)

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause(0.2)

            self.assertEqual(status_text(app), "○ Not downloaded · 1.5 GB")
            self.assertEqual(str(button(app).label), "[Download]")

    async def test_not_downloaded_without_the_hub_shows_no_size(self):
        repository = FakeSettingsRepository(
            make_status(InstinctModelState.NOT_DOWNLOADED), None
        )
        app = RowTestApp(repository)

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause(0.2)

            self.assertEqual(status_text(app), "○ Not downloaded")

    async def test_downloading_shows_progress_and_cancel(self):
        progress = DownloadProgress(bytes_done=630_000_000, bytes_total=MODEL_BYTES)
        repository = FakeSettingsRepository(
            make_status(InstinctModelState.DOWNLOADING, download_progress=progress),
            MODEL_BYTES,
        )
        app = RowTestApp(repository)

        async with app.run_test() as pilot:
            await pilot.pause(0.2)

            self.assertIn("Downloading", status_text(app))
            self.assertIn("━━━━━━━━────────────", status_text(app))
            self.assertTrue(status_text(app).endswith("42% · 630 MB of 1.5 GB"))
            self.assertEqual(str(button(app).label), "[Cancel]")

    async def test_ready_names_the_device_and_has_no_button(self):
        repository = FakeSettingsRepository(
            make_status(InstinctModelState.READY, running_device="cuda"), MODEL_BYTES
        )
        app = RowTestApp(repository)

        async with app.run_test() as pilot:
            await pilot.pause(0.2)

            self.assertEqual(status_text(app), "✓ Ready · running on cuda")
            self.assertFalse(button(app).display)

    async def test_failed_download_shows_the_reason_and_retry(self):
        failure = InstinctFailure("download", "no connection to huggingface.co")
        repository = FakeSettingsRepository(
            make_status(InstinctModelState.FAILED, failure=failure), MODEL_BYTES
        )
        app = RowTestApp(repository)

        async with app.run_test() as pilot:
            await pilot.pause(0.2)

            self.assertEqual(
                status_text(app),
                "✗ Download failed: no connection to huggingface.co",
            )
            self.assertEqual(str(button(app).label), "[Retry]")

    async def test_download_button_starts_the_download(self):
        repository = FakeSettingsRepository(
            make_status(InstinctModelState.NOT_DOWNLOADED), MODEL_BYTES
        )
        app = RowTestApp(repository)

        async with app.run_test() as pilot:
            await pilot.pause(0.2)
            await pilot.click("#instinct-status-button")

            self.assertEqual(repository.download_calls, 1)
            self.assertEqual(repository.cancel_calls, 0)

    async def test_cancel_button_cancels_a_running_download(self):
        repository = FakeSettingsRepository(
            make_status(InstinctModelState.DOWNLOADING), MODEL_BYTES
        )
        app = RowTestApp(repository)

        async with app.run_test() as pilot:
            await pilot.pause(0.2)
            await pilot.click("#instinct-status-button")

            self.assertEqual(repository.cancel_calls, 1)
            self.assertEqual(repository.download_calls, 0)
