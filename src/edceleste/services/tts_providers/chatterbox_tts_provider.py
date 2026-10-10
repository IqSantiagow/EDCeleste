import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np

from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    SettingsIssueModel,
    TtsProviderParams,
)
from edceleste.services.tts_providers.tts_provider_protocol import (
    CloningTTSProviderProtocol,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from chatterbox.tts_turbo import ChatterboxTurboTTS


class ChatterboxTTSProvider(CloningTTSProviderProtocol):
    # Chatterbox learns a voice from the first 10 seconds of a clip
    reference_seconds = 10.0
    profile_file_extension = ".pt"

    def __init__(self) -> None:
        """Only sets the state of the loaded model. The model is loaded on the
        first use, not here, because loading takes seconds and a lot of memory.
        The settings are not stored, they come with every call."""
        self.model: "ChatterboxTurboTTS | None" = None
        self.loaded_device: str | None = None
        self.loaded_nano: bool | None = None
        self.loaded_profile_path: Path | None = None

    async def synthesize(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> tuple[np.ndarray, int]:
        """Speaks the text with the voice profile in profile_path.

        1. Loads the model if needed, or again when device or nano differ from
           the loaded model. This may download it from the Hugging Face Hub the
           first time.
        2. Loads the voice profile into the model when it is not the loaded one.
        3. Generates the speech in a worker thread with the exaggeration and
           cfg_weight from params.
        Returns the samples and the sample rate, plays nothing. Raises
        TypeError for params of another provider, ValueError when
        profile_path is None and FileNotFoundError for a missing profile file.
        """
        if not isinstance(params, ChatterboxParamsModel):
            raise TypeError(
                f"Chatterbox needs ChatterboxParamsModel, got {type(params)}"
            )
        if profile_path is None:
            raise ValueError("Chatterbox needs a voice profile.")

        model = await asyncio.to_thread(self.__get_or_load_model, params)
        await asyncio.to_thread(self.__load_voice_profile_into_model, profile_path)

        output = await asyncio.to_thread(
            model.generate,
            text=text,
            norm_loudness=False,
            exaggeration=params.exaggeration,
            cfg_weight=params.cfg_weight,
        )
        return output.squeeze(0).cpu().numpy(), model.sr

    async def create_voice_profile(
        self,
        reference_audio_path: str,
        profile_path: Path,
        params: TtsProviderParams,
    ) -> None:
        """Lets the model learn the voice from the clip and saves it as a .pt
        file in profile_path. Loads the model if needed. Raises TypeError for
        params of another provider.

        Side effect: the model now speaks with the new voice, but
        loaded_profile_path is cleared, so the next synthesize() loads the
        profile from the file.
        """
        if not isinstance(params, ChatterboxParamsModel):
            raise TypeError(
                f"Chatterbox needs ChatterboxParamsModel, got {type(params)}"
            )

        model = await asyncio.to_thread(self.__get_or_load_model, params)
        await asyncio.to_thread(
            model.prepare_conditionals,
            wav_fpath=reference_audio_path,
            norm_loudness=False,
        )
        model.conds.save(profile_path)
        self.loaded_profile_path = None

    def validate_params(self, params: TtsProviderParams) -> SettingsIssueModel | None:
        """Only checks that a profile name is set. Does not check that the
        profile file exists, a missing file shows up on the first sentence.
        Raises TypeError for params of another provider."""
        if not isinstance(params, ChatterboxParamsModel):
            raise TypeError(
                f"Chatterbox needs ChatterboxParamsModel, got {type(params)}"
            )

        if not params.profile:
            return SettingsIssueModel(
                section="tts",
                field="profile",
                message="Profile is not set.",
            )
        return None

    def get_available_device(self) -> Literal["cuda", "cpu"]:
        """What the "auto" device setting turns into: "cuda" when torch sees a
        GPU, otherwise "cpu"."""
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def __load_model(self, params: ChatterboxParamsModel) -> None:
        """Loads Chatterbox Turbo on the device from params ("auto" -> see
        get_available_device) and with the nano flag. Slow and blocking. The
        first time, from_pretrained downloads the model from the Hugging Face
        Hub. The new model has no voice profile, so loaded_profile_path is
        cleared."""
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        logger.info("Preparing Chatterbox TTS model...")

        device = params.device
        if device not in ["cpu", "cuda"]:
            device = self.get_available_device()

        self.model = ChatterboxTurboTTS.from_pretrained(device=device, nano=params.nano)
        self.loaded_device = params.device
        self.loaded_nano = params.nano
        self.loaded_profile_path = None

    def __get_or_load_model(
        self, params: ChatterboxParamsModel
    ) -> "ChatterboxTurboTTS":
        """Loads the model on the first call (slow, blocking) and again when
        device or nano in params differ from the loaded model. Otherwise returns
        the loaded one. Raises RuntimeError when loading left no model."""
        is_other_model_wanted = (
            self.loaded_device != params.device or self.loaded_nano != params.nano
        )
        if self.model is None or is_other_model_wanted:
            self.__load_model(params)

        if self.model is None:
            raise RuntimeError("Chatterbox TTS model could not be prepared.")

        return self.model

    def __load_voice_profile_into_model(self, profile_path: Path) -> None:
        """Makes the model speak with the profile: reads the .pt file into
        model.conds. Does nothing when this profile is already loaded. Blocking.
        Raises FileNotFoundError when the profile file does not exist."""
        from chatterbox.tts_turbo import Conditionals

        if self.model is None:
            raise RuntimeError(
                "Chatterbox TTS model is not loaded. "
                "You tried to load a voice profile without a model."
            )
        if self.loaded_profile_path == profile_path:
            return

        if not profile_path.exists():
            raise FileNotFoundError(f"Voice profile not found: {profile_path}")

        self.model.conds = Conditionals.load(profile_path, self.model.device)
        self.loaded_profile_path = profile_path
