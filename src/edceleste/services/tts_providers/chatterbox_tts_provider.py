import asyncio
import logging
import os
from typing import TYPE_CHECKING, Literal
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
        voice_profile_path = self.VOICES_DIR / self.provider_settings.profile

        if not voice_profile_path.exists():
            raise FileNotFoundError(
                f"Voice profile '{self.provider_settings.profile}' not found in "
                f"{self.VOICES_DIR}"
            )

        model.conds = Conditionals.load(Path(voice_profile_path), model.device)
        self.is_profile_prepared = True

    def clone_voice(self, path_to_audio_file: str, profile_name: str) -> None:
        model = self.__get_prepared_model()
        voices_path = self.VOICES_DIR

        if not voices_path.exists():
            voices_path.mkdir(parents=True, exist_ok=True)

        if not os.path.isfile(path_to_audio_file):
            raise FileNotFoundError(f"Audio file '{path_to_audio_file}' not found.")

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

        try:
            sf.write(
                trimmed_clip_path,
                audio_data,
                samplerate,
                subtype=audio_info.subtype,
            )

            model.prepare_conditionals(wav_fpath=trimmed_clip_path, norm_loudness=False)

            profile_file_name = add_pt_file_extension_if_missing(
                Path(profile_name).name
            )
            model.conds.save(Path(voices_path) / profile_file_name)

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
        voices_path = self.VOICES_DIR

        if not voices_path.exists():
            return []

        profiles = [
            f.name
            for f in voices_path.iterdir()
            if f.is_file() and f.name.endswith(".pt")
        ]

        return profiles
