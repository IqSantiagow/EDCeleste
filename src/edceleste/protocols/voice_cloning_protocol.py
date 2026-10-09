from typing import Protocol
from typing import AsyncGenerator
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    VoiceAnalysisResult,
    VoiceCloningState,
)


class VoiceCloningProtocol(Protocol):
    """Voice profiles exist only for the chatterbox TTS provider. With another
    provider active every method raises VoiceCloningException, except
    get_available_profiles(), which returns an empty list. A profile is a
    "<name>.pt" file plus a "<name>_sample.wav" file in the voices folder.
    None of the methods change the settings, even for the active profile."""

    # Plain def: an async generator is iterated with "async for", never awaited
    def clone_voice(
        self, path_to_audio_file: str, profile_name: str
    ) -> "AsyncGenerator[VoiceCloningState, None]":
        """Slow, loads the voice model on first use. Takes the first 10 s of
        the audio file and makes a profile from it. Yields the steps in this
        order: DIRECTORY_CREATED, AUDIO_PROCESSED, COMPLETED, SAMPLE_CREATED.
        A profile with the same name is overwritten. Raises FileNotFoundError
        for a missing file, ValueError for a clip shorter than 10 s and
        RuntimeError when the model part fails. The errors come while
        iterating, not on the call."""
        ...

    def get_available_profiles(self) -> list[str]:
        """Reads the voices folder on disk. Names come without ".pt". Empty
        when the folder does not exist yet."""
        ...

    def remove_profile(self, profile_name: str) -> None:
        """Deletes the profile file and its sample file from disk. A missing
        file is skipped, not an error."""
        ...

    def rename_profile(self, old_profile_name: str, new_profile_name: str) -> None:
        """Renames the profile file and its sample file on disk, nothing is
        cloned again. Raises FileExistsError when the new name is taken."""
        ...

    async def preview_voice_sample(self, profile_name: str, text: str) -> None:
        """Generates speech for any text with the profile (slow, loads the
        voice model on first use), adds the voice lab effects and the volume,
        plays it and waits until it ends."""
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
        self, path_to_audio_file: str
    ) -> VoiceAnalysisResult:
        """Blocking, reads the whole file. Measures the clip for the clone
        dialog: length, channels, peak, clipping, noise floor and the waveform
        bars. A clip shorter than 10 s is not an error, it comes back with
        is_valid=False and a message. A file that cannot be read raises."""
        ...
