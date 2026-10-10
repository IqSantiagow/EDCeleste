from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import numpy as np

from edceleste.services.models.settings_model import (
    SettingsIssueModel,
    TtsProviderParams,
)

"""
For a future myself. Every adapter, extension or some kind of provider which
wants to integrate with service absolutely cannot rely on config and cannot
store app config as it is.

The app architecture relies heavily on sending the settings when they are
explicity validated and saved. When adapter/extension relies on it, then it is
forced to use old state while the UI shows forms/values that are not yet applied.
Example is cloning a voice when user is switching a provider. Chatterbox while
cloning tries to access settings which are not yet emmited from the UI.

The solution is to always pass the settings explicitly to functions and never
store them directly within the provider.

A provider only turns text into samples. Files, folders, effects and playing
belong to TTSService.
"""


class TTSProviderProtocol(Protocol):
    async def synthesize(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> tuple[np.ndarray, int]:
        """Turns the text into speech and returns (samples, sample_rate). Plays
        nothing and adds no effects. params are the settings of this provider
        type, a provider raises TypeError for the params of another one.
        profile_path is the voice profile file, only cloning providers use it."""
        ...

    def validate_params(self, params: TtsProviderParams) -> SettingsIssueModel | None:
        """Checks only the fields of this provider type. None means fine."""
        ...


@runtime_checkable
class CloningTTSProviderProtocol(TTSProviderProtocol, Protocol):
    reference_seconds: float
    profile_file_extension: str

    async def create_voice_profile(
        self,
        reference_audio_path: str,
        profile_path: Path,
        params: TtsProviderParams,
    ) -> None:
        """Learns the voice from the reference clip (about reference_seconds
        long) and saves the profile in profile_path, in the format of this
        provider. The folder of profile_path already exists."""
        ...

    def get_available_device(self) -> Literal["cuda", "cpu"]:
        """What the "auto" device setting turns into on this machine."""
        ...
