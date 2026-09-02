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
    """Loudest single sample in the clip, in dBFS (0 dBFS = full scale)."""
    peak_amplitude = float(np.max(np.abs(audio_samples)))
    if peak_amplitude == 0:
        return SILENCE_FLOOR_DBFS
    return 20 * np.log10(peak_amplitude)


def calculate_noise_floor_dbfs(audio_samples: np.ndarray, sample_rate: int) -> float:
    """Background noise level: RMS loudness of the quietest 100ms window."""
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
    """Peak amplitude per short window, for drawing a waveform sparkline."""
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
    if profile_file_name.endswith(".pt"):
        return profile_file_name
    return profile_file_name + ".pt"


def find_voices_directory(operating_system_name: str = os.name) -> Path:
    """Voice profiles are stored in the per-user application data directory."""
    if operating_system_name == "nt":
        application_data_directory = Path(os.environ["LOCALAPPDATA"])
    else:
        application_data_directory = Path.home() / ".local" / "share"

    return application_data_directory / "EDCeleste" / "voices"


class ChatterboxTTSProvider(TTSProviderProtocol):
    model: "ChatterboxTurboTTS | None" = None
    is_profile_prepared: bool = False

    VOICES_DIR = find_voices_directory()

    def __init__(self, config: SettingsModel):
        self.config = config

    @property
    def provider_settings(self) -> ChatterboxTTSProviderModel:
        return self.config.tts.provider  # type: ignore[return-value]

    async def synthesize(self, text: str) -> None:
        import sounddevice as sd

        model = self.__get_prepared_model()

        if not self.is_profile_prepared:
            await asyncio.to_thread(self.prepare_model_with_profile)

        output = await asyncio.to_thread(
            model.generate,
            text=text,
            norm_loudness=False,
            exaggeration=self.provider_settings.exaggeration,
            cfg_weight=self.provider_settings.cfg_weight,
        )

        output_numpy = output.squeeze(0).cpu().numpy()

        sd.play(output_numpy * self.config.tts.volume, model.sr)

        await asyncio.sleep(len(output_numpy) / model.sr)

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        if not new_settings.tts.provider.profile:  # type: ignore[union-attr]
            return SettingsIssueModel(
                section="tts",
                field="profile",
                message="Profile is not set.",
            )
        return None

    def get_available_device(self) -> Literal["cuda", "cpu"]:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def __prepare_model(self):
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        logger.info("Preparing Chatterbox TTS model...")

        device = self.provider_settings.device
        if device not in ["cpu", "cuda"]:
            device = self.get_available_device()
        self.model = ChatterboxTurboTTS.from_pretrained(
            device=device, nano=self.provider_settings.nano
        )

    def __get_prepared_model(self) -> "ChatterboxTurboTTS":
        if self.model is None:
            self.__prepare_model()

        if self.model is None:
            raise RuntimeError("Chatterbox TTS model could not be prepared.")

        return self.model

    def prepare_model_with_profile(self):
        from chatterbox.tts_turbo import Conditionals

        model = self.__get_prepared_model()
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
        model = await asyncio.to_thread(self.__get_prepared_model)
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

            await self.prepare_sample_voice(profile_name)

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
        already done and saved, this just moves 2 small files."""
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
        from chatterbox.tts_turbo import Conditionals

        model = self.__get_prepared_model()

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

    async def prepare_sample_voice(
        self, profile_name: str, text: str = DEFAULT_VOICE_SAMPLE_TEXT
    ) -> None:
        samples, sample_rate = await self.__generate_speech_for_profile(
            profile_name, text
        )

        profile_file_name = profile_name + "_sample.wav"
        sample_path = self.__build_profile_path(profile_file_name)
        sf.write(sample_path, samples, sample_rate)

    async def preview_voice_sample(self, profile_name: str, text: str) -> None:
        import sounddevice as sd

        samples, sample_rate = await self.__generate_speech_for_profile(
            profile_name, text
        )

        sd.play(samples * self.config.tts.volume, sample_rate)
        await asyncio.sleep(len(samples) / sample_rate)

    async def play_sample_voice(self, profile_name: str) -> None:
        profile_file_name = profile_name + "_sample.wav"
        profile_path = self.__build_profile_path(profile_file_name)

        if not profile_path.exists():
            raise FileNotFoundError(
                f"Profile '{profile_name}' not found at '{profile_path}'."
            )

        await self.play_audio_file(str(profile_path))

    async def play_audio_file(self, path_to_audio_file: str) -> None:
        import sounddevice as sd

        audio_samples, sample_rate = sf.read(path_to_audio_file)

        sd.play(audio_samples * self.config.tts.volume, sample_rate)

        await asyncio.sleep(len(audio_samples) / sample_rate)

    def __build_profile_path(self, profile_name: str) -> Path:
        voices_path = self.VOICES_DIR
        return Path(voices_path) / Path(profile_name).name

    def perform_sample_voice_analysis_and_validate(
        self, path_to_audio_file: str
    ) -> VoiceAnalysisResult:
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
