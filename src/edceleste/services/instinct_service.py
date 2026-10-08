from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
import time
from dataclasses import replace
from typing import TYPE_CHECKING, AsyncGenerator, Literal

import httpx

from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
    DownloadCancelled,
)
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

if TYPE_CHECKING:
    from decider.infer import Decider

logger = logging.getLogger(__name__)

SECONDS_BETWEEN_PROGRESS_UPDATES = 0.2

DeviceChoice = Literal["auto", "cuda", "cpu"]

WARM_UP_QUESTIONS = {
    "warm_up": {
        "type": "noul",
        "instructions": "Did the pilot ask for a ship action?",
        "criteria": {"true": "yes", "false": "no"},
    }
}


class ModelNotDownloaded(Exception):
    pass


# transformers swaps these for flash-linear-attention kernels, which run only on the GPU
GPU_ONLY_KERNELS = ["torch_chunk_gated_delta_rule", "torch_recurrent_gated_delta_rule"]
gpu_kernels: dict = {}


def switch_qwen_kernels_to_device(device: str) -> None:
    from transformers.models.qwen3_5 import modeling_qwen3_5

    for kernel_name in GPU_ONLY_KERNELS:
        gpu_kernel = gpu_kernels.setdefault(
            kernel_name, getattr(modeling_qwen3_5, kernel_name)
        )
        kernel = gpu_kernel if device == "cuda" else inspect.unwrap(gpu_kernel)
        setattr(modeling_qwen3_5, kernel_name, kernel)


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
    decider: Decider | None = None
    device_choice: DeviceChoice = "auto"

    def __init__(
        self,
        settings_service: SettingsService,
        download_service: DecisionModelDownloadService,
    ) -> None:
        self.settings_service = settings_service
        self.download_service = download_service

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        return None

    def reload_service(self) -> None:
        instinct_settings = self.settings_service.get_settings().llm.instinct
        self.enabled = instinct_settings.enabled
        self.change_device(instinct_settings.device)
        if self.enabled:
            self.download_and_load_model_in_background()
        else:
            self.unload_model()

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
                await asyncio.to_thread(self.warm_up)
        except DownloadCancelled:
            logger.info("Instinct model download cancelled.")
        except Exception as error:
            logger.exception("Instinct model %s failed", step)
            self.failure = InstinctFailure(step, describe_failure_reason(error))
        finally:
            self.download_progress = None

    def get_download_size(self) -> int | None:
        if self.download_size is None:
            try:
                self.download_size = self.download_service.get_download_size()
            except Exception:
                # without the Hub the row says just "Not downloaded"
                logger.warning("Cannot ask the Hub for the model size", exc_info=True)
        return self.download_size

    # ----- The model itself -----

    def change_device(self, device_choice: DeviceChoice) -> None:
        if device_choice != self.device_choice:
            self.unload_model()  # loaded again on the new device by the next call
        self.device_choice = device_choice

    def unload_model(self) -> None:
        if self.decider is None:
            return
        self.decider = None
        import torch

        torch.cuda.empty_cache()  # give the GPU memory back to the game

    def running_device(self) -> str | None:
        return str(self.decider.dev) if self.decider is not None else None

    def load_model(self) -> Decider:
        if self.decider is not None:
            return self.decider
        if not self.download_service.is_model_downloaded():
            raise ModelNotDownloaded("The Instinct model is not downloaded yet.")
        import torch
        from decider.infer import Decider

        device = self.device_choice
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        switch_qwen_kernels_to_device(device)
        start = time.perf_counter()
        self.decider = Decider(str(self.download_service.model_folder), device=device)
        if self.decider.eng is not None and importlib.util.find_spec("triton") is None:
            # torch.compile needs Triton; without it run the slower eager forward
            logger.warning(
                "Triton is missing, the decision model runs without compile."
            )
            self.decider.eng._fwd_impl = self.decider.eng._fwd_eager
        logger.info(
            "Decision model loaded on %s in %.1f s",
            self.decider.dev,
            time.perf_counter() - start,
        )
        return self.decider

    def ask(self, state: dict, questions: dict) -> dict:
        decider = self.load_model()
        start = time.perf_counter()
        answers = decider.system_one(state, questions)["answers"]
        logger.info(
            "Decision model: %s -> %s in %.0f ms",
            state.get("pilot_said") or state.get("event"),
            answers,
            (time.perf_counter() - start) * 1000,
        )
        return answers

    def warm_up(self) -> None:
        state = {"game_state": "", "pilot_said": "deploy hardpoints"}
        self.ask(state, WARM_UP_QUESTIONS)

    # ----- Status for the UI and the cold start -----

    def get_status(self) -> InstinctStatus:
        return InstinctStatus(
            state=self.get_model_state(),
            download_progress=self.download_progress,
            running_device=self.running_device(),
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
