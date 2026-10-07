import asyncio
import logging
from dataclasses import replace
from typing import AsyncGenerator, Literal

import httpx

from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
    DownloadCancelled,
)
from edceleste.services.local_decision_model_service import LocalDecisionModelService
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.instinct_status import (
    DownloadProgress,
    InstinctFailure,
    InstinctModelState,
    InstinctStatus,
    describe_download_progress,
)
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

SECONDS_BETWEEN_PROGRESS_UPDATES = 0.2


def describe_failure_reason(error: Exception) -> str:
    if isinstance(error, (httpx.ConnectError, httpx.TimeoutException)):
        return "no connection to huggingface.co"
    first_line = str(error).splitlines()[0] if str(error) else type(error).__name__
    return first_line[:120]


class InstinctService:
    enabled: bool = False
    background_task: asyncio.Task | None = None
    download_progress: DownloadProgress | None = None
    failure: InstinctFailure | None = None
    download_size: int | None = None

    def __init__(
        self,
        settings_service: SettingsService,
        download_service: DecisionModelDownloadService,
        model_service: LocalDecisionModelService,
    ) -> None:
        self.settings_service = settings_service
        self.download_service = download_service
        self.model_service = model_service

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        return None  # Enabled and Device cannot be invalid

    def reload_service(self) -> None:
        instinct_settings = self.settings_service.get_settings().llm.instinct
        self.enabled = instinct_settings.enabled
        self.model_service.change_device(instinct_settings.device)
        if self.enabled:
            self.download_and_load_model_in_background()
        else:
            self.model_service.unload_model()

    def download_and_load_model_in_background(self) -> None:
        if self.is_busy():
            return
        self.failure = None
        self.background_task = asyncio.create_task(self.download_and_load_model())

    def cancel_download(self) -> None:
        self.download_service.cancel_download()

    def is_busy(self) -> bool:
        return self.background_task is not None and not self.background_task.done()

    async def download_and_load_model(self) -> None:
        step: Literal["download", "load"] = "download"
        try:
            if not self.download_service.is_model_downloaded():
                async for progress in self.download_service.download_model():
                    self.download_progress = progress
            step = "load"
            if self.enabled:
                await asyncio.to_thread(self.model_service.warm_up)
        except DownloadCancelled:
            logger.info("Instinct model download cancelled.")
        except Exception as error:
            logger.exception("Instinct model %s failed", step)
            self.failure = InstinctFailure(step, describe_failure_reason(error))
        finally:
            self.download_progress = None

    def get_status(self) -> InstinctStatus:
        return InstinctStatus(
            state=self.get_model_state(),
            download_progress=self.download_progress,
            running_device=self.model_service.running_device(),
            failure=self.failure,
        )

    def get_model_state(self) -> InstinctModelState:
        is_downloaded = self.download_service.is_model_downloaded()
        if self.is_busy():
            if is_downloaded:
                return InstinctModelState.LOADING
            return InstinctModelState.DOWNLOADING
        if self.failure:
            return InstinctModelState.FAILED
        if is_downloaded:
            return InstinctModelState.READY
        return InstinctModelState.NOT_DOWNLOADED

    def get_download_size(self) -> int | None:
        if self.download_size is None:
            try:
                self.download_size = self.download_service.get_download_size()
            except Exception:
                # without the Hub the row says just "Not downloaded"
                logger.warning("Cannot ask the Hub for the model size", exc_info=True)
        return self.download_size

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        status = ColdStartStatus(
            service="instinct",
            message=None,
            is_critical=False,
            completed=False,
        )
        yield status

        self.reload_service()
        if not self.enabled:
            yield replace(status, completed=True, is_disabled=True)
            return

        while self.is_busy():
            if self.download_progress:
                progress_text = describe_download_progress(self.download_progress)
                yield replace(
                    status, progress_text=f"Downloading model {progress_text}"
                )
            await asyncio.sleep(SECONDS_BETWEEN_PROGRESS_UPDATES)

        if self.failure is None:
            yield replace(status, completed=True)
            return
        # Not critical: without Instinct every command goes through Celeste
        failed_step = (
            "model download failed"
            if self.failure.step == "download"
            else "model failed to load"
        )
        yield replace(
            status,
            completed=True,
            is_warning=True,
            message=f"{failed_step} ({self.failure.reason}). "
            "Commands go through Celeste.",
        )
