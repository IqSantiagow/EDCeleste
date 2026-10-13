from collections.abc import AsyncIterator
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
class StreamingTTSProviderProtocol(TTSProviderProtocol, Protocol):
    stream_sample_rate: int  # in Hz, the sample rate of every piece

    def can_stream(self, params: TtsProviderParams) -> bool:
        """True when speaking in pieces is better than speaking the whole text
        at once for these params, e.g. false on a machine too slow to make
        audio faster than it is played. Must be cheap and must not load a
        model: TTSService asks it before every sentence. A provider raises
        TypeError for the params of another provider."""
        ...

    def synthesize_stream(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> AsyncIterator[np.ndarray]:
        """Like synthesize(), but gives the speech in pieces as soon as each
        one is ready: mono float32 samples at stream_sample_rate. The first
        piece comes long before the whole text is done. Plays nothing and adds
        no effects. Not an `async def`: it returns an async iterator, read it
        with `async for`, without `await`. The iterator ends after the last
        piece, and a text with no sound gives no pieces. Errors about the
        params or the profile are raised before the first piece, an error while
        the speech is made comes out of the iteration."""
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
