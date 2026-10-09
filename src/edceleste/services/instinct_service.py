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
    """Changes global state: swaps functions inside the transformers qwen3_5
    module, so it affects every Qwen model in the process. Called right
    before the model is loaded.

    The first call saves the original GPU kernels in gpu_kernels. "cuda" puts
    the GPU kernels back, any other device puts in the plain torch version
    hidden under the GPU wrapper, which also runs on the CPU.
    """
    from transformers.models.qwen3_5 import modeling_qwen3_5

    for kernel_name in GPU_ONLY_KERNELS:
        gpu_kernel = gpu_kernels.setdefault(
            kernel_name, getattr(modeling_qwen3_5, kernel_name)
        )
        kernel = gpu_kernel if device == "cuda" else inspect.unwrap(gpu_kernel)
        setattr(modeling_qwen3_5, kernel_name, kernel)


def describe_failure_reason(error: Exception) -> str:
    """Short reason shown in the settings row and the cold start warning.
    No connection or a timeout -> "no connection to huggingface.co".
    Anything else -> the first line of the error text cut to 120 characters,
    or the exception class name when the text is empty."""
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
        """Only stores the dependencies. Nothing is downloaded or loaded here,
        that starts in reload_service()."""
        self.settings_service = settings_service
        self.download_service = download_service

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Always None. enabled and device are already limited by the
        settings model, so Instinct never blocks saving the settings."""
        return None

    def reload_service(self) -> None:
        """Applies the saved Instinct settings. Called by cold_start() and
        after the settings change.

        1. Stores enabled and the device. A new device unloads the model.
        2. Enabled -> starts the download and load in a background task and
           returns at once, it does not wait for the task.
           Disabled -> unloads the model and frees the GPU memory. A download
           that is already running is not cancelled, it finishes, but the
           model is not loaded after it.
        """
        instinct_settings = self.settings_service.get_settings().llm.instinct
        self.enabled = instinct_settings.enabled
        self.change_device(instinct_settings.device)
        if self.enabled:
            self.download_and_load_model_in_background()
        else:
            self.unload_model()

    def download_and_load_model_in_background(self) -> None:
        """Starts download_and_load_model() as an asyncio task and returns at
        once. Needs a running event loop.
        Does nothing while the previous task still runs. Clears the last
        failure, so the UI stops showing it."""
        if self.is_busy():
            return
        self.failure = None
        self.background_task = asyncio.create_task(self.download_and_load_model())

    def cancel_download(self) -> None:
        """Only raises the cancel flag in the download service. The download
        stops at its next chunk, deletes the half downloaded files, and
        download_and_load_model() ends without a failure."""
        self.download_service.cancel_download()

    def is_busy(self) -> bool:
        """True while the background download and load task runs. A finished,
        failed or cancelled task is not busy."""
        return self.background_task is not None and not self.background_task.done()

    async def download_and_load_model(self) -> None:
        """Body of the background task. Goes to the network.

        1. When the model is not on disk yet, downloads it from the Hugging
           Face Hub and keeps the newest progress in download_progress, so the
           UI and cold_start() can show it.
        2. When Instinct is still enabled, loads the model and asks one warm up
           question in a worker thread, so the first real command is fast.

        Errors are not raised. A cancelled download is only logged. Any other
        error is logged and saved in failure, together with the step that failed
        ("download" or "load"). download_progress is always cleared at the end.
        """
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

    def fetch_download_size(self) -> int | None:
        """Model size in bytes, for the "Not downloaded" row in settings.

        The first call asks the Hugging Face Hub over the network and blocks,
        later calls return the saved answer. Returns None when the Hub cannot
        be reached. That error is logged, not raised, and the next call asks
        the Hub again."""
        if self.download_size is None:
            try:
                self.download_size = self.download_service.fetch_download_size()
            except Exception:
                # without the Hub the row says just "Not downloaded"
                logger.warning("Cannot ask the Hub for the model size", exc_info=True)
        return self.download_size

    # ----- The model itself -----

    def change_device(self, device_choice: DeviceChoice) -> None:
        """A different device unloads the model, the same device keeps it. The
        model is not loaded again here, only by the next load_model() call."""
        if device_choice != self.device_choice:
            self.unload_model()  # loaded again on the new device by the next call
        self.device_choice = device_choice

    def unload_model(self) -> None:
        """Forgets the loaded model and empties the CUDA cache. Does nothing
        when no model is loaded. The files on disk stay."""
        if self.decider is None:
            return
        self.decider = None
        import torch

        torch.cuda.empty_cache()  # give the GPU memory back to the game

    def running_device(self) -> str | None:
        """Device the loaded model really runs on, e.g. "cuda" or "cpu", so
        the settings row can show where "auto" ended up. None when no model is
        loaded."""
        return str(self.decider.dev) if self.decider is not None else None

    def load_model(self) -> Decider:
        """Loads the model on the first call, later calls return the same one.
        Slow and blocking, so callers run it in a worker thread.

        1. Raises ModelNotDownloaded when the files are not on disk. It never
           downloads anything.
        2. "auto" becomes "cuda" when torch sees a GPU, otherwise "cpu".
        3. Switches the Qwen kernels to that device.
        4. Loads the model. Without Triton, torch.compile cannot run, so the
           slower eager forward is used.
        """
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

    def ask_decision_model(self, state: dict, questions: dict) -> dict:
        """Runs the local model once. Blocking, and slow when the model is not
        loaded yet, because it loads it first (errors like ModelNotDownloaded
        are raised). Logs what the pilot said or which event came, the answers
        and how long it took.

        state holds e.g. "game_state" and "pilot_said". questions maps a
        question name to its type, instructions and criteria, see
        WARM_UP_QUESTIONS. The answers are keyed by the same question names.
        """
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
        """Loads the model and asks one made up question, so the slow first
        run happens at startup and not on the pilot's first command. The answer
        is thrown away. Blocking."""
        state = {"game_state": "", "pilot_said": "deploy hardpoints"}
        self.ask_decision_model(state, WARM_UP_QUESTIONS)

    # ----- Status for the UI and the cold start -----

    def get_status(self) -> InstinctStatus:
        """Snapshot for the Instinct row in settings. Checks the disk to see
        if the model is downloaded."""
        return InstinctStatus(
            state=self.get_model_state(),
            download_progress=self.download_progress,
            running_device=self.running_device(),
            failure=self.failure,
        )

    def get_model_state(self) -> InstinctModelState:
        """Picks the one state the UI shows, first match wins:
        1. background task runs -> LOADING when the files are on disk,
           otherwise DOWNLOADING,
        2. the last task failed -> FAILED,
        3. files are on disk -> READY, even when the model is not in memory,
        4. otherwise NOT_DOWNLOADED.
        """
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
        """Startup check shown in the system check screen. May download the
        model, which can take minutes.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Applies the settings (reload_service). Disabled -> yields completed
           with is_disabled and stops.
        3. Enabled -> waits for the background download and load, and yields
           the download progress every 0.2 s.
        4. Yields completed. A failed download or load is only a warning with
           the reason, never critical, because without Instinct every command
           still goes through Celeste.
        """
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
