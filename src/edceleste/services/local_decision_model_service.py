from __future__ import annotations

import importlib.util
import inspect
import logging
import time
from typing import TYPE_CHECKING, Literal

from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
)

if TYPE_CHECKING:
    from decider.infer import Decider

logger = logging.getLogger(__name__)

DeviceChoice = Literal["auto", "cuda", "cpu"]

# The first call compiles the model (~30 s once), so warm_up asks this one
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


class LocalDecisionModelService:
    decider: Decider | None = None
    device_choice: DeviceChoice = "auto"

    def __init__(self, download_service: DecisionModelDownloadService) -> None:
        self.download_service = download_service

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
