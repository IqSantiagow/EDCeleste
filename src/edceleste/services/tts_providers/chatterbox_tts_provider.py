import asyncio
from enum import Enum, auto
import logging
import os
from typing import TYPE_CHECKING, AsyncGenerator, Literal, TypedDict
import numpy as np
import soundfile as sf
from edceleste.services.models.settings_model import (
    ChatterboxTTSProviderModel,
    SettingsIssueModel,
    SettingsModel,
)
from edceleste.services.tts_providers.tts_provider_protocol import TTSProviderProtocol
from edceleste.services.voice_lab_service import VoiceLabService
from pathlib import Path

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from chatterbox.tts_turbo import ChatterboxTurboTTS

MINIMUM_REFERENCE_AUDIO_SECONDS = 10.0
RECOMMENDED_REFERENCE_AUDIO_SECONDS_RANGE = (10.0, 30.0)
DEFAULT_VOICE_SAMPLE_TEXT = "Hello Commander. How can I assist you today?"

# How much audio goes into one waveform bar. Small enough to look smooth,
# big enough that a 30s file does not send thousands of numbers to the UI.
WAVEFORM_ENVELOPE_WINDOW_SECONDS = 0.1

# Below this amplitude, audio is treated as silence for dBFS math (avoids
# log10(0) blowing up on fully silent clips).
SILENCE_FLOOR_DBFS = -120.0


class VoiceCloningState(Enum):
    DIRECTORY_CREATED = auto()
    AUDIO_PROCESSED = auto()
    COMPLETED = auto()
    SAMPLE_CREATED = auto()


class VoiceAnalysisResult(TypedDict):
    file_name: str
    duration_seconds: float
    sample_rate: int
    channels: int
    is_mono: bool
    peak_dbfs: float
    has_clipping: bool
    noise_floor_dbfs: float
    waveform_envelope: list[float]
    is_valid: bool
    validation_error_message: str | None


def calculate_peak_dbfs(audio_samples: np.ndarray) -> float:
    """Loudest single sample in the clip, in dBFS (0 dBFS = full scale).
    A fully silent clip gives SILENCE_FLOOR_DBFS."""
    peak_amplitude = float(np.max(np.abs(audio_samples)))
    if peak_amplitude == 0:
        return SILENCE_FLOOR_DBFS
    return 20 * np.log10(peak_amplitude)


def calculate_noise_floor_dbfs(audio_samples: np.ndarray, sample_rate: int) -> float:
    """Background noise level: RMS loudness of the quietest 100ms window.
    Stereo is mixed to mono first. A fully silent window gives
    SILENCE_FLOOR_DBFS."""
    mono_samples = (
        audio_samples if audio_samples.ndim == 1 else audio_samples.mean(axis=1)
    )
    window_size = max(1, int(sample_rate * 0.1))
    window_count = max(1, len(mono_samples) // window_size)

    quietest_window_rms = min(
        float(
            np.sqrt(
                np.mean(
                    mono_samples[i * window_size : (i + 1) * window_size].astype(
                        np.float64
                    )
                    ** 2
                )
            )
        )
        for i in range(window_count)
    )

    if quietest_window_rms == 0:
        return SILENCE_FLOOR_DBFS
    return 20 * np.log10(quietest_window_rms)


def calculate_waveform_envelope(
    audio_samples: np.ndarray,
    sample_rate: int,
    window_seconds: float = WAVEFORM_ENVELOPE_WINDOW_SECONDS,
) -> list[float]:
    """Peak amplitude per short window, for drawing a waveform sparkline.
    Stereo is mixed to mono first. A last window shorter than the others is
    left out."""
    mono_samples = (
        audio_samples if audio_samples.ndim == 1 else audio_samples.mean(axis=1)
    )
    window_size = max(1, int(sample_rate * window_seconds))
    window_count = max(1, len(mono_samples) // window_size)

    return [
        float(np.max(np.abs(mono_samples[i * window_size : (i + 1) * window_size])))
        for i in range(window_count)
    ]


def add_pt_file_extension_if_missing(profile_file_name: str) -> str:
    """Profile names in settings and the UI come without ".pt", the files on
    disk have it. Safe to call twice, "x.pt" stays "x.pt"."""
    if profile_file_name.endswith(".pt"):
        return profile_file_name
    return profile_file_name + ".pt"


def find_voices_directory(operating_system_name: str = os.name) -> Path:
    """Voice profiles are stored in the per-user application data directory:
    %LOCALAPPDATA%\\EDCeleste\\voices on Windows ("nt"), otherwise
    ~/.local/share/EDCeleste/voices. Only builds the path, the folder is
    created later by clone_voice()."""
    if operating_system_name == "nt":
        application_data_directory = Path(os.environ["LOCALAPPDATA"])
    else:
        application_data_directory = Path.home() / ".local" / "share"

    return application_data_directory / "EDCeleste" / "voices"


class ChatterboxTTSProvider(TTSProviderProtocol):
    model: "ChatterboxTurboTTS | None" = None
    is_profile_prepared: bool = False

    VOICES_DIR = find_voices_directory()

    def __init__(self, config: SettingsModel, voice_lab_service: VoiceLabService):
        """Only stores the settings. The model is loaded on the first use, not
        here, because loading takes seconds and a lot of memory. config is the
        whole SettingsModel, because the volume lives in config.tts."""
        self.config = config
        self.voice_lab_service = voice_lab_service

    @property
    def provider_settings(self) -> ChatterboxTTSProviderModel:
        """config.tts.provider narrowed to the Chatterbox model. TTSService
        builds this provider only when the type is "chatterbox", so the cast
        is safe."""
        return self.config.tts.provider  # type: ignore[return-value]

    async def synthesize_and_play(self, text: str) -> None:
        """Speaks the text with the voice profile from settings.

        1. Loads the model if needed. This blocks the event loop and may
           download it from the Hugging Face Hub the first time.
        2. Loads the voice profile into the model once, in a worker thread.
        3. Generates the speech in a worker thread with the exaggeration and
           cfg_weight from settings.
        4. Adds the Voice Lab effects, plays it at the configured volume and
           waits until it has played.
        Errors are raised, e.g. FileNotFoundError for a missing profile.
        """
        import sounddevice as sd

        model = self.__get_or_load_model()

        if not self.is_profile_prepared:
            await asyncio.to_thread(self.load_voice_profile_into_model)

        output = await asyncio.to_thread(
            model.generate,
            text=text,
            norm_loudness=False,
            exaggeration=self.provider_settings.exaggeration,
            cfg_weight=self.provider_settings.cfg_weight,
        )

        output_numpy = self.voice_lab_service.apply_effects(
            output.squeeze(0).cpu().numpy(), model.sr
        )

        sd.play(output_numpy * self.config.tts.volume, model.sr)

        await asyncio.sleep(len(output_numpy) / model.sr)

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Only checks that a profile name is set. Does not check that the
        profile file exists, a missing file shows up on the first sentence."""
        if not new_settings.tts.provider.profile:  # type: ignore[union-attr]
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

    def __load_model(self):
        """Loads Chatterbox Turbo on the device from settings ("auto" -> see
        get_available_device) and with the nano flag. Slow and blocking. The
        first time, from_pretrained downloads the model from the Hugging Face
        Hub. Does not load the voice profile and does not reset
        is_profile_prepared."""
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        logger.info("Preparing Chatterbox TTS model...")

        device = self.provider_settings.device
        if device not in ["cpu", "cuda"]:
            device = self.get_available_device()
        self.model = ChatterboxTurboTTS.from_pretrained(
            device=device, nano=self.provider_settings.nano
        )

    def __get_or_load_model(self) -> "ChatterboxTurboTTS":
        """Loads the model on the first call (slow, blocking), later calls
        return the same one. Raises RuntimeError when loading left no model."""
        if self.model is None:
            self.__load_model()

        if self.model is None:
            raise RuntimeError("Chatterbox TTS model could not be prepared.")

        return self.model

    def load_voice_profile_into_model(self):
        """Makes the model speak with the profile from settings: reads the
        profile's .pt file from the voices folder into model.conds and marks
        the profile as prepared. Blocking, loads the model first if needed.
        Raises FileNotFoundError when the profile file does not exist."""
        from chatterbox.tts_turbo import Conditionals

        model = self.__get_or_load_model()
        voice_profile_path = self.__build_profile_path(
            add_pt_file_extension_if_missing(self.provider_settings.profile)
        )

        if not voice_profile_path.exists():
            raise FileNotFoundError(
                f"Voice profile '{self.provider_settings.profile}' not found in "
                f"{self.VOICES_DIR}"
            )

        model.conds = Conditionals.load(Path(voice_profile_path), model.device)
        self.is_profile_prepared = True

    async def clone_voice(
        self, path_to_audio_file: str, profile_name: str
    ) -> AsyncGenerator[VoiceCloningState, None]:
        """Makes a new voice profile from a recording. Writes files to the
        voices folder and yields after every step, so the UI can show
        progress.

        1. Loads the model in a worker thread and creates the voices folder.
           Raises FileNotFoundError when the audio file does not exist.
           Yields DIRECTORY_CREATED.
        2. Raises ValueError when the clip is shorter than 10 s. Reads only
           the first 10 s of it. Yields AUDIO_PROCESSED.
        3. Writes those 10 s next to the profiles and lets the model learn the
           voice from them. Yields COMPLETED, but the profile is not saved yet.
        4. Saves the profile as <name>.pt and generates <name>_sample.wav with
           DEFAULT_VOICE_SAMPLE_TEXT. Yields SAMPLE_CREATED.

        Side effect: the model now speaks with the cloned voice (model.conds),
        but is_profile_prepared is not changed. Any error in steps 3 and 4 is
        raised again as RuntimeError. The trimmed 10 s clip is always deleted.
        """
        model = await asyncio.to_thread(self.__get_or_load_model)
        voices_path = self.VOICES_DIR

        if not voices_path.exists():
            voices_path.mkdir(parents=True, exist_ok=True)

        if not os.path.isfile(path_to_audio_file):
            raise FileNotFoundError(f"Audio file '{path_to_audio_file}' not found.")

        yield VoiceCloningState.DIRECTORY_CREATED

        audio_info = sf.info(path_to_audio_file)
        audio_duration = audio_info.frames / audio_info.samplerate

        if audio_duration < MINIMUM_REFERENCE_AUDIO_SECONDS:
            raise ValueError(
                f"Audio file '{path_to_audio_file}' is too short. "
                f"It must be at least {MINIMUM_REFERENCE_AUDIO_SECONDS} seconds long."
            )

        soundfile_name = os.path.basename(path_to_audio_file)
        trimmed_clip_path = os.path.join(voices_path, soundfile_name)

        frames_to_read = int(MINIMUM_REFERENCE_AUDIO_SECONDS * audio_info.samplerate)
        audio_data, samplerate = sf.read(path_to_audio_file, frames=frames_to_read)

        yield VoiceCloningState.AUDIO_PROCESSED
        try:
            sf.write(
                trimmed_clip_path,
                audio_data,
                samplerate,
                subtype=audio_info.subtype,
            )

            await asyncio.to_thread(
                model.prepare_conditionals,
                wav_fpath=trimmed_clip_path,
                norm_loudness=False,
            )

            yield VoiceCloningState.COMPLETED

            profile_file_name = add_pt_file_extension_if_missing(
                Path(profile_name).name
            )
            model.conds.save(self.__build_profile_path(profile_file_name))

            await self.generate_and_save_voice_sample(profile_name)

            yield VoiceCloningState.SAMPLE_CREATED

        except Exception as e:
            raise RuntimeError(
                f"Failed to prepare voice profile '{profile_name}' "
                f"from audio file '{soundfile_name}'."
            ) from e

        finally:
            if os.path.exists(trimmed_clip_path):
                os.remove(trimmed_clip_path)

    def reload_provider(self, new_settings: SettingsModel):
        """Stores the new settings and throws away only what they make stale:
        - a new profile -> the profile is loaded again before the next sentence,
        - a new device or nano flag -> the model is loaded again on next use.
        Anything else, e.g. volume or exaggeration, keeps the loaded model."""
        previous_provider_settings = self.provider_settings
        self.config = new_settings

        if previous_provider_settings.profile != self.provider_settings.profile:
            self.is_profile_prepared = False

        if (
            previous_provider_settings.device != self.provider_settings.device
            or previous_provider_settings.nano != self.provider_settings.nano
        ):
            self.model = None

    def get_available_profiles(self) -> list[str]:
        """
        The ".pt" extension is just how profile files happen to be stored on
        disk, the UI should never see it. Voice profile names shown to the
        user (and stored in settings) are always without ".pt".
        Reads the voices folder. Empty when the folder does not exist yet.
        """
        voices_path = self.VOICES_DIR

        if not voices_path.exists():
            return []

        profiles = [
            f.name.removesuffix(".pt")
            for f in voices_path.iterdir()
            if f.is_file() and f.name.endswith(".pt")
        ]

        return profiles

    def remove_profile(self, profile_name: str) -> None:
        """Deletes <name>.pt and <name>_sample.wav from the voices folder. A
        file that is not there is skipped, so removing a missing profile does
        not fail. The settings are not changed, they may still point at it."""
        profile_file_name = add_pt_file_extension_if_missing(profile_name)
        profile_file_sample_name = profile_name + "_sample.wav"
        profile_path = self.__build_profile_path(profile_file_name)
        profile_sample_path = self.__build_profile_path(profile_file_sample_name)

        if profile_path.exists():
            profile_path.unlink()

        if profile_sample_path.exists():
            profile_sample_path.unlink()

    def rename_profile(self, old_profile_name: str, new_profile_name: str) -> None:
        """Cheap rename on disk - the expensive part (the embeddings) is
        already done and saved, this just moves 2 small files.
        Raises FileExistsError when the new name is taken and
        FileNotFoundError when the old profile does not exist. A missing sample
        is skipped. The settings are not changed."""
        old_profile_path = self.__build_profile_path(
            add_pt_file_extension_if_missing(old_profile_name)
        )
        new_profile_path = self.__build_profile_path(
            add_pt_file_extension_if_missing(new_profile_name)
        )

        if new_profile_path.exists():
            raise FileExistsError(f"Voice profile '{new_profile_name}' already exists.")

        old_profile_path.rename(new_profile_path)

        old_sample_path = self.__build_profile_path(old_profile_name + "_sample.wav")
        new_sample_path = self.__build_profile_path(new_profile_name + "_sample.wav")
        if old_sample_path.exists():
            old_sample_path.rename(new_sample_path)

    async def __generate_speech_for_profile(
        self, profile_name: str, text: str
    ) -> tuple[np.ndarray, int]:
        """Generates speech with any saved profile, not only the one from
        settings. Returns the samples and the sample rate, plays nothing.

        Side effect: loads that profile into model.conds, so the model keeps
        speaking with it afterwards. is_profile_prepared is not changed, so
        when it was True, synthesize_and_play() does not switch back to the profile
        from settings.
        """
        from chatterbox.tts_turbo import Conditionals

        model = self.__get_or_load_model()

        profile_path = self.__build_profile_path(
            add_pt_file_extension_if_missing(profile_name)
        )
        model.conds = Conditionals.load(Path(profile_path), model.device)

        output = await asyncio.to_thread(
            model.generate,
            text=text,
            norm_loudness=False,
            exaggeration=self.provider_settings.exaggeration,
            cfg_weight=self.provider_settings.cfg_weight,
        )
        return output.squeeze(0).cpu().numpy(), model.sr

    async def generate_and_save_voice_sample(
        self, profile_name: str, text: str = DEFAULT_VOICE_SAMPLE_TEXT
    ) -> None:
        """Generates the text with the profile's voice and writes it to
        <name>_sample.wav in the voices folder, replacing an older sample.
        Plays nothing and adds no Voice Lab effects."""
        samples, sample_rate = await self.__generate_speech_for_profile(
            profile_name, text
        )

        profile_file_name = profile_name + "_sample.wav"
        sample_path = self.__build_profile_path(profile_file_name)
        sf.write(sample_path, samples, sample_rate)

    async def preview_voice_sample(self, profile_name: str, text: str) -> None:
        """Speaks the text with the profile's voice, the Voice Lab effects and
        the configured volume, and waits until it has played. Nothing is
        written to disk, so the saved sample stays as it is."""
        import sounddevice as sd

        samples, sample_rate = await self.__generate_speech_for_profile(
            profile_name, text
        )
        samples = self.voice_lab_service.apply_effects(samples, sample_rate)

        sd.play(samples * self.config.tts.volume, sample_rate)
        await asyncio.sleep(len(samples) / sample_rate)

    async def play_sample_voice(self, profile_name: str) -> None:
        """Plays the saved <name>_sample.wav, no speech is generated and no
        model is loaded. Raises FileNotFoundError when there is no sample."""
        profile_file_name = profile_name + "_sample.wav"
        profile_path = self.__build_profile_path(profile_file_name)

        if not profile_path.exists():
            raise FileNotFoundError(
                f"Profile '{profile_name}' not found at '{profile_path}'."
            )

        await self.play_audio_file(str(profile_path))

    async def play_audio_file(self, path_to_audio_file: str) -> None:
        """Plays the file at the configured volume, without Voice Lab effects,
        and waits until it has played. Reading the file blocks the event
        loop."""
        import sounddevice as sd

        audio_samples, sample_rate = sf.read(path_to_audio_file)

        sd.play(audio_samples * self.config.tts.volume, sample_rate)

        await asyncio.sleep(len(audio_samples) / sample_rate)

    def __build_profile_path(self, profile_name: str) -> Path:
        """Takes a file name, e.g. "x.pt" or "x_sample.wav", and puts it in the
        voices folder. Any folder part of the name is dropped, so a name like
        "../x" cannot reach outside the voices folder. Does not check that the
        file exists."""
        voices_path = self.VOICES_DIR
        return Path(voices_path) / Path(profile_name).name

    def perform_sample_voice_analysis_and_validate(
        self, path_to_audio_file: str
    ) -> VoiceAnalysisResult:
        """Reads the whole file and measures it for the clone screen: length,
        sample rate, channels, peak and noise floor in dBFS, clipping (peak at
        0 dBFS or more) and a waveform for the sparkline. Loads no model.

        Only the length decides is_valid: shorter than 10 s -> is_valid False
        with a message. Clipping, stereo or noise never make it invalid, the UI
        only shows them as hints. A missing or broken file raises.
        """
        audio_info = sf.info(path_to_audio_file)
        audio_duration_seconds = audio_info.frames / audio_info.samplerate
        audio_samples, _ = sf.read(path_to_audio_file, always_2d=False)

        validation_error_message = None
        if audio_duration_seconds < MINIMUM_REFERENCE_AUDIO_SECONDS:
            recommended_min, recommended_max = RECOMMENDED_REFERENCE_AUDIO_SECONDS_RANGE
            validation_error_message = (
                f"Too short - minimum {MINIMUM_REFERENCE_AUDIO_SECONDS:.0f}s, "
                f"recommended {recommended_min:.0f}-{recommended_max:.0f}s"
            )

        peak_dbfs = calculate_peak_dbfs(audio_samples)

        return VoiceAnalysisResult(
            file_name=os.path.basename(path_to_audio_file),
            duration_seconds=audio_duration_seconds,
            sample_rate=audio_info.samplerate,
            channels=audio_info.channels,
            is_mono=audio_info.channels == 1,
            peak_dbfs=peak_dbfs,
            has_clipping=peak_dbfs >= 0.0,
            noise_floor_dbfs=calculate_noise_floor_dbfs(
                audio_samples, audio_info.samplerate
            ),
            waveform_envelope=calculate_waveform_envelope(
                audio_samples, audio_info.samplerate
            ),
            is_valid=validation_error_message is None,
            validation_error_message=validation_error_message,
        )
