import asyncio
import itertools
import logging
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from pocket_tts_onnx import PocketTTS

from edceleste.services.models.settings_model import (
    PocketParamsModel,
    SettingsIssueModel,
    TtsProviderParams,
)
from edceleste.services.tts_providers.tts_provider_protocol import (
    CloningTTSProviderProtocol,
    StreamingTTSProviderProtocol,
)

logger = logging.getLogger(__name__)

# The model file (228 MB, int8) and the exact version of it. A new model is a new
# app release, as with Instinct.
MODEL_REPO = "thewh1teagle/pocket-tts-onnx"
MODEL_REVISION = "110f5251188e9407b4f724acdd8b0dfd0b20692a"
MODEL_FILE = "pocket-tts-english.onnx"
# Measured on an i7-13700K: 2 threads 1.9x faster than real time, 4 threads 2.1x,
# 6 threads 2.7x. 4 leave the rest of the processor to the game.
ONNX_THREADS = 4
# Steps of the flow part of the model. This model file is made with up to 4 and
# pays for all 4 whatever is asked, so 4 are free.
DECODE_STEPS = 4
# The pieces of audio the voice is given in. The first one is 4 frames of 80 ms,
# and a smaller one left a gap before the next piece came. The next ones are 6
# frames, 480 ms each.
FIRST_PIECE_FRAMES = 4
NEXT_PIECE_FRAMES = 6
# The model has to make speech this many times faster than it is played, or
# the pieces come late and the voice stutters
MIN_REAL_TIME_FACTOR = 1.3
# A shorter speech does not tell the speed: the first step of a text is slower
MIN_SPEECH_SECONDS_TO_JUDGE_SPEED = 2.0
# The model carries on from the end of the voice clip, so the clip must end in
# silence. The app cuts a clip after 10 seconds, and one clip was cut in the
# middle of an "s": every speech then began with that hiss (50-120 ms of noise
# before the first word). With this silence after the clip it was gone in every
# try.
SILENCE_AFTER_CLIP_SECONDS = 0.5
# The decoder of the model starts every speech with the same tick, whatever the
# text: 8 samples (0.3 ms, about -42 dBFS). In a silent room it is heard as a
# click before the voice, and the Voice Lab does not remove it. The speech comes
# in from silence over this time.
FADE_IN_SECONDS = 0.010


def find_or_download_model_file() -> Path:
    """The path of the model file on disk. Looks in the Hugging Face cache
    first, so a model that was downloaded once needs no network. Otherwise
    downloads it (228 MB, slow) without a token. Network errors are raised."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        return Path(
            hf_hub_download(
                MODEL_REPO,
                MODEL_FILE,
                revision=MODEL_REVISION,
                token=False,
                local_files_only=True,
            )
        )
    except LocalEntryNotFoundError:
        return Path(
            hf_hub_download(
                MODEL_REPO, MODEL_FILE, revision=MODEL_REVISION, token=False
            )
        )


def take_frames(frames: Iterator[np.ndarray], count: int) -> list[np.ndarray]:
    """The next `count` frames, or fewer when the speech ends. Blocking: every
    frame is made by the model while this runs."""
    return list(itertools.islice(frames, count))


def fade_in_the_start_of_the_speech(
    samples: np.ndarray, sample_rate: int
) -> np.ndarray:
    """A copy of samples whose first FADE_IN_SECONDS rise in a straight line
    from silence to the original level, which hides the tick the decoder of the
    model makes at the very start of a speech. The rest is the same, and the
    array that was passed in is not changed. Samples shorter than the fade rise
    over their whole length, and no samples give no samples."""
    fade_samples = min(len(samples), int(FADE_IN_SECONDS * sample_rate))
    faded = samples.copy()
    rising = np.linspace(0.0, 1.0, fade_samples, endpoint=False, dtype=samples.dtype)
    faded[:fade_samples] *= rising
    return faded


class PocketTTSProvider(CloningTTSProviderProtocol, StreamingTTSProviderProtocol):
    # The voice is learned from the first 10 seconds of a clip
    reference_seconds = 10.0
    # The voice profile is the array the voice encoder makes, saved by numpy
    profile_file_extension = ".npy"
    profile_folder_name = "pocket"
    # The audio decoder always makes 24 kHz
    stream_sample_rate = 24000

    def __init__(self) -> None:
        """Only sets the state. The model is loaded on the first use, not
        here, because loading takes seconds (and a download the first time).
        The settings are not stored, they come with every call."""
        self.engine: PocketTTS | None = None
        self.voice: np.ndarray | None = None
        self.loaded_profile_path: Path | None = None
        self.is_too_slow = False

    async def synthesize(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> tuple[np.ndarray, int]:
        """Speaks the whole text with the voice profile in profile_path.

        1. Loads the model if needed (this may download it the first time) and
           the voice profile when it is not the loaded one.
        2. Makes all the frames in a worker thread and joins them.
        3. Fades in the first FADE_IN_SECONDS (see fade_in_the_start_of_the_speech).
        Returns the samples and the sample rate, plays nothing. Raises
        TypeError for params of another provider, ValueError when profile_path
        is None and FileNotFoundError for a missing profile file. A text with no
        sound gives no samples.
        """
        self.__raise_for_wrong_params_or_missing_profile_path(params, profile_path)
        assert profile_path is not None
        if text.strip() == "":
            return np.zeros(0, dtype=np.float32), self.stream_sample_rate

        engine = await asyncio.to_thread(self.__get_or_load_engine)
        await asyncio.to_thread(self.__set_voice_from_profile_file, profile_path)

        frames = await asyncio.to_thread(
            list, engine.stream(text, voice=self.voice, decode_steps=DECODE_STEPS)
        )
        if not frames:
            return np.zeros(0, dtype=np.float32), engine.sample_rate
        speech = np.concatenate(frames)
        faded_speech = fade_in_the_start_of_the_speech(speech, engine.sample_rate)
        return faded_speech, engine.sample_rate

    async def synthesize_stream(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> AsyncIterator[np.ndarray]:
        """Speaks the text with the voice profile in profile_path, in pieces:
        the first one is FIRST_PIECE_FRAMES frames long (320 ms), the next ones
        NEXT_PIECE_FRAMES (480 ms). The first piece comes after about 150 ms,
        the rest is made while the pilot already hears it.

        1. Loads the model and the voice profile exactly as synthesize() does.
        2. In a worker thread takes the frames of one piece from the model, so
           the event loop stays free, and gives the piece: mono float32 at
           stream_sample_rate. The first piece is faded in over the first
           FADE_IN_SECONDS (see fade_in_the_start_of_the_speech), the next ones
           are given as the model made them.
        3. After the last piece judges the speed: when the model made a speech
           of 2 seconds or more less than MIN_REAL_TIME_FACTOR times faster
           than it is played, can_stream() says False from now on. Only the
           time inside the model counts, not the time the caller took between
           pieces. A caller that stops reading early gets no judgement.
        Plays nothing and adds no effects. Read the pieces with `async for`,
        without `await`.

        Raises TypeError for params of another provider, ValueError when
        profile_path is None and FileNotFoundError for a missing profile file,
        all at the first step of the `async for`, before the first piece. Errors
        while the model is loaded (no network the first time) come out the same
        way. A text with no sound gives no pieces.
        """
        self.__raise_for_wrong_params_or_missing_profile_path(params, profile_path)
        assert profile_path is not None
        if text.strip() == "":
            return

        engine = await asyncio.to_thread(self.__get_or_load_engine)
        await asyncio.to_thread(self.__set_voice_from_profile_file, profile_path)

        frames = engine.stream(text, voice=self.voice, decode_steps=DECODE_STEPS)
        frames_in_piece = FIRST_PIECE_FRAMES
        samples_made = 0
        seconds_in_model = 0.0
        while True:
            started = time.perf_counter()
            piece_frames = await asyncio.to_thread(take_frames, frames, frames_in_piece)
            seconds_in_model += time.perf_counter() - started
            if not piece_frames:
                break
            piece = np.concatenate(piece_frames)
            if samples_made == 0:
                piece = fade_in_the_start_of_the_speech(piece, engine.sample_rate)
            samples_made += len(piece)
            yield piece
            frames_in_piece = NEXT_PIECE_FRAMES

        speech_seconds = samples_made / engine.sample_rate
        if speech_seconds >= MIN_SPEECH_SECONDS_TO_JUDGE_SPEED:
            real_time_factor = speech_seconds / seconds_in_model
            self.is_too_slow = real_time_factor < MIN_REAL_TIME_FACTOR

    def can_stream(self, params: TtsProviderParams) -> bool:
        """True until a speech was made too slowly to be played in pieces (see
        synthesize_stream). Cheap: loads no model. TTSService asks it before
        every sentence, and a False makes it speak the whole text at once.
        Raises TypeError for params of another provider."""
        if not isinstance(params, PocketParamsModel):
            raise TypeError(f"Pocket TTS needs PocketParamsModel, got {type(params)}")
        return not self.is_too_slow

    async def create_voice_profile(
        self,
        reference_audio_path: str,
        profile_path: Path,
        params: TtsProviderParams,
    ) -> None:
        """Lets the voice encoder learn the voice from the clip in
        reference_audio_path and saves it to the file profile_path (an .npy
        file, its folder must exist). A file already there is replaced, the
        caller checks the name first.
        1. Loads the model in a worker thread if needed (slow, and it may
           download the model the first time).
        2. Clears loaded_profile_path, because the file is about to change.
        3. Reads the clip, mixes it down to mono, adds SILENCE_AFTER_CLIP_SECONDS
           of silence after it, learns the voice and saves it as float16, which
           is how the model stores its own voices.

        Raises TypeError for params of another provider, before anything is
        loaded. A clip that cannot be read, or an error of the model, comes out
        as it is and nothing is saved.
        """
        if not isinstance(params, PocketParamsModel):
            raise TypeError(f"Pocket TTS needs PocketParamsModel, got {type(params)}")

        engine = await asyncio.to_thread(self.__get_or_load_engine)
        self.loaded_profile_path = None
        await asyncio.to_thread(
            self.__learn_voice_from_clip_and_save_profile_file,
            engine,
            reference_audio_path,
            profile_path,
        )

    def validate_params(self, params: TtsProviderParams) -> SettingsIssueModel | None:
        """Only checks that a profile name is set. Returns a SettingsIssueModel
        for section "tts", field "profile" and the message "Profile is not set."
        when the name is empty, and None when it is fine. Does not check that
        the profile file exists (TTSService.validate_settings does that, and a
        missing file shows up on the first sentence otherwise). Raises
        TypeError for params of another provider."""
        if not isinstance(params, PocketParamsModel):
            raise TypeError(f"Pocket TTS needs PocketParamsModel, got {type(params)}")

        if not params.profile:
            return SettingsIssueModel(
                section="tts",
                field="profile",
                message="Profile is not set.",
            )
        return None

    def get_available_device(self) -> Literal["cuda", "cpu"]:
        """What the "auto" device setting turns into: always "cpu", because
        Pocket TTS runs on the processor only, whatever the machine has."""
        return "cpu"

    def __raise_for_wrong_params_or_missing_profile_path(
        self, params: TtsProviderParams, profile_path: Path | None
    ) -> None:
        """The checks every speech starts with. Raises TypeError for params of
        another provider and ValueError when profile_path is None."""
        if not isinstance(params, PocketParamsModel):
            raise TypeError(f"Pocket TTS needs PocketParamsModel, got {type(params)}")
        if profile_path is None:
            raise ValueError("Pocket TTS needs a voice profile.")

    def __get_or_load_engine(self) -> PocketTTS:
        """Loads the model on the first call (slow, blocking, it may download
        the file) and keeps it. Later calls give the loaded one."""
        if self.engine is None:
            logger.info("Preparing Pocket TTS model...")
            self.engine = PocketTTS(
                find_or_download_model_file(), num_threads=ONNX_THREADS
            )
        return self.engine

    def __set_voice_from_profile_file(self, profile_path: Path) -> None:
        """Reads the .npy file of the profile into self.voice, the voice every
        speech uses. Does nothing when this profile is already loaded.
        Blocking. Raises FileNotFoundError when the profile file does not
        exist."""
        if self.loaded_profile_path == profile_path:
            return

        if not profile_path.exists():
            raise FileNotFoundError(f"Voice profile not found: {profile_path}")

        self.voice = np.load(profile_path, allow_pickle=False)
        self.loaded_profile_path = profile_path

    def __learn_voice_from_clip_and_save_profile_file(
        self, engine: PocketTTS, reference_audio_path: str, profile_path: Path
    ) -> None:
        """Blocking part of create_voice_profile(), run in a worker thread.
        1. Reads the clip from reference_audio_path as float32 with soundfile.
        2. Mixes a stereo clip down to mono (the average of the channels).
        3. Adds SILENCE_AFTER_CLIP_SECONDS of silence after the clip, counted
           in the sample rate of the clip. The model carries on from the end
           of the clip, and a clip that ends in the middle of a sound (the app
           cuts it after 10 seconds) starts every speech with that sound.
        4. Lets the model learn the voice from the clip and the silence, at the
           sample rate of the clip (the model resamples it itself).
        5. Saves the voice as float16 in profile_path, replacing a file that is
           already there.
        Reads and writes the disk and runs the model, so it blocks. A clip that
        soundfile cannot read raises its error, and nothing is saved then."""
        samples, sample_rate = sf.read(reference_audio_path, dtype="float32")
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        silence = np.zeros(int(SILENCE_AFTER_CLIP_SECONDS * sample_rate), np.float32)
        samples = np.concatenate([samples, silence])
        voice = engine.clone_voice(samples, sample_rate=sample_rate)
        np.save(profile_path, voice.astype(np.float16))
