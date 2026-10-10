from typing import Protocol
from typing import AsyncGenerator
from edceleste.services.models.settings_model import TtsProviderParams
from edceleste.services.models.voice_cloning_models import (
    VoiceAnalysisResult,
    VoiceCloningState,
)


class VoiceCloningProtocol(Protocol):
    """Voice profiles exist only for TTS providers that clone voices (chatterbox).
    The methods that get params work for the provider the pilot has picked on
    the screen, saved or not. With params of another provider they raise
    VoiceCloningException, except get_available_profiles(), which returns an
    empty list. A profile is a "<name>.pt" file plus a "<name>_sample.wav" file
    in the voices folder. None of the methods change the settings, even for the
    active profile."""

    # Plain def: an async generator is iterated with "async for", never awaited
    def clone_voice(
        self, path_to_audio_file: str, profile_name: str, params: TtsProviderParams
    ) -> AsyncGenerator[VoiceCloningState, None]:
        """Slow, loads the voice model on first use. Takes the first seconds of
        the audio file and makes a profile from it. params are the settings as
        they are on the screen now (e.g. an unsaved device), not the saved
        ones. Yields the steps in this
        order: DIRECTORY_CREATED, AUDIO_PROCESSED, COMPLETED, SAMPLE_CREATED.
        A profile with the same name is never overwritten, that raises
        FileExistsError. Raises FileNotFoundError
        for a missing file, ValueError for a clip shorter than the provider
        needs (10 s for Chatterbox), RuntimeError when the model part fails
        and VoiceCloningException when the provider of params cannot clone.
        The errors come while iterating, not on the call."""
        ...

    def get_available_profiles(self, params: TtsProviderParams) -> list[str]:
        """Reads the voices folder on disk. Names come without ".pt". Empty
        when the folder does not exist yet."""
        ...

    def remove_profile(self, profile_name: str, params: TtsProviderParams) -> None:
        """Deletes the profile file and its sample file from disk. A missing
        file is skipped, not an error."""
        ...

    def rename_profile(
        self, old_profile_name: str, new_profile_name: str, params: TtsProviderParams
    ) -> None:
        """Renames the profile file and its sample file on disk, nothing is
        cloned again. Raises FileExistsError when the new name is taken."""
        ...

    async def preview_voice_sample(
        self, profile_name: str, text: str, params: TtsProviderParams
    ) -> None:
        """Generates speech for any text with the profile (slow, loads the
        voice model on first use), adds the volume, plays it and waits until it
        ends. params are the settings as they are on the screen now."""
        ...

    async def play_sample_voice(self, profile_name: str) -> None:
        """Plays the sample made when the profile was cloned, nothing is
        generated. Waits until it ends. Raises FileNotFoundError when the
        sample file is missing."""
        ...

    async def play_audio_file(self, path_to_audio_file: str) -> None:
        """Plays any audio file with the volume from the settings but without
        voice lab effects, e.g. the clip the pilot picked before cloning. Waits
        until it ends."""
        ...

    def perform_sample_voice_analysis_and_validate(
        self, path_to_audio_file: str, params: TtsProviderParams
    ) -> VoiceAnalysisResult:
        """Blocking, reads the whole file. Measures the clip for the clone
        dialog: length, channels, peak, clipping, noise floor and the waveform
        bars. A clip shorter than the provider of params needs (10 s for
        Chatterbox) is not an error, it comes back with
        is_valid=False and a message. A file that cannot be read raises."""
        ...
