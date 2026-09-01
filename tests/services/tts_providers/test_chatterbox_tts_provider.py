import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import torch  # noqa: F401  (kept in sys.modules while chatterbox is faked)
import soundfile as sf

from edceleste.services.models.settings_model import (
    ChatterboxTTSProviderModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from edceleste.services.tts_providers import chatterbox_tts_provider
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)

PROFILE_NAME = "celeste"
CLIP_SAMPLERATE = 8000


def _make_settings(
    profile: str = PROFILE_NAME,
    volume: float = 1.0,
    device: str = "auto",
    nano: bool = True,
) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(
            provider=ChatterboxTTSProviderModel(
                type="chatterbox",
                profile=profile,
                device=device,
                nano=nano,
            ),
            volume=volume,
        ),
        llm=LLMModel(system_prompt="sp", user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


def _make_model_mock(generated_samples: np.ndarray) -> Mock:
    generated_waveform = Mock()
    generated_waveform.squeeze.return_value.cpu.return_value.numpy.return_value = (
        generated_samples
    )

    model = Mock()
    model.sr = 24000
    model.generate.return_value = generated_waveform

    return model


def _install_fake_chatterbox_module(test_case: unittest.TestCase) -> Mock:
    # The real chatterbox package is heavy, so it is replaced by a stub that
    # only records how the model and the voice profile were asked to be built.
    fake_tts_turbo_module = Mock()

    modules_patcher = patch.dict(
        sys.modules,
        {
            "chatterbox": Mock(),
            "chatterbox.tts_turbo": fake_tts_turbo_module,
        },
    )
    modules_patcher.start()
    test_case.addCleanup(modules_patcher.stop)

    return fake_tts_turbo_module


def _write_audio_clip(path: str, seconds: float) -> None:
    samples = np.zeros(int(seconds * CLIP_SAMPLERATE), dtype="float32")
    sf.write(path, samples, CLIP_SAMPLERATE, subtype="PCM_16")


class ChatterboxTTSProviderSynthesizeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # sounddevice needs a working PortAudio install; fake the module so
        # tests run on systems (like headless CI) that don't have it.
        self.fake_sounddevice_module = MagicMock()
        sounddevice_patcher = patch.dict(
            sys.modules, {"sounddevice": self.fake_sounddevice_module}
        )
        sounddevice_patcher.start()
        self.addCleanup(sounddevice_patcher.stop)
        self.mock_sd_play = self.fake_sounddevice_module.play

        self.generated_samples = np.array([0.1, 0.2, 0.3])
        self.model = _make_model_mock(self.generated_samples)

        self.provider = ChatterboxTTSProvider(_make_settings())
        self.provider.model = self.model
        self.provider.is_profile_prepared = True

    async def test_synthesize_generates_speech_from_the_given_text(self):
        await self.provider.synthesize("Hello Commander")

        self.model.generate.assert_called_once_with(
            text="Hello Commander",
            norm_loudness=False,
            exaggeration=self.provider.provider_settings.exaggeration,
            cfg_weight=self.provider.provider_settings.cfg_weight,
        )

    async def test_synthesize_plays_generated_samples_at_model_samplerate(self):
        await self.provider.synthesize("Hello Commander")

        played_samples, played_samplerate = self.mock_sd_play.call_args.args
        np.testing.assert_allclose(played_samples, self.generated_samples)
        self.assertEqual(played_samplerate, self.model.sr)

    async def test_synthesize_scales_generated_samples_by_configured_volume(self):
        self.provider.config = _make_settings(volume=0.5)

        await self.provider.synthesize("Hello Commander")

        played_samples, _ = self.mock_sd_play.call_args.args
        np.testing.assert_allclose(played_samples, self.generated_samples * 0.5)

    async def test_synthesize_prepares_the_voice_profile_only_once(self):
        self.provider.is_profile_prepared = False
        self.provider.prepare_model_with_profile = Mock(
            side_effect=lambda: setattr(self.provider, "is_profile_prepared", True)
        )

        await self.provider.synthesize("Hello Commander")
        await self.provider.synthesize("Fuel level low")

        self.provider.prepare_model_with_profile.assert_called_once()

    async def test_synthesize_loads_the_model_on_the_configured_device(self):
        fake_tts_turbo_module = _install_fake_chatterbox_module(self)
        fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained.return_value = (
            self.model
        )
        self.provider.config = _make_settings(device="cpu", nano=False)
        self.provider.model = None

        await self.provider.synthesize("Hello Commander")

        fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained.assert_called_once_with(
            device="cpu", nano=False
        )

    async def test_synthesize_falls_back_to_cpu_when_cuda_is_unavailable(self):
        fake_tts_turbo_module = _install_fake_chatterbox_module(self)
        fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained.return_value = (
            self.model
        )
        self.provider.model = None

        with patch("torch.cuda.is_available", return_value=False):
            await self.provider.synthesize("Hello Commander")

        fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained.assert_called_once_with(
            device="cpu", nano=True
        )

    async def test_synthesize_picks_cuda_when_it_is_available(self):
        fake_tts_turbo_module = _install_fake_chatterbox_module(self)
        fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained.return_value = (
            self.model
        )
        self.provider.model = None

        with patch("torch.cuda.is_available", return_value=True):
            await self.provider.synthesize("Hello Commander")

        fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained.assert_called_once_with(
            device="cuda", nano=True
        )


class ChatterboxTTSProviderVoiceProfileTest(unittest.TestCase):
    def setUp(self):
        self.fake_tts_turbo_module = _install_fake_chatterbox_module(self)

        self.voices_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.voices_directory.cleanup)

        self.model = Mock()
        self.model.device = "cpu"

        self.provider = ChatterboxTTSProvider(_make_settings())
        self.provider.model = self.model
        self.provider.VOICES_DIR = Path(self.voices_directory.name)

    def test_prepare_model_with_profile_raises_when_the_profile_does_not_exist(self):
        with self.assertRaises(FileNotFoundError):
            self.provider.prepare_model_with_profile()

        self.assertFalse(self.provider.is_profile_prepared)

    def test_prepare_model_with_profile_loads_the_saved_conditionals(self):
        profile_path = Path(self.voices_directory.name) / f"{PROFILE_NAME}.pt"
        profile_path.touch()
        loaded_conditionals = Mock()
        self.fake_tts_turbo_module.Conditionals.load.return_value = loaded_conditionals

        self.provider.prepare_model_with_profile()

        self.fake_tts_turbo_module.Conditionals.load.assert_called_once_with(
            profile_path, "cpu"
        )
        self.assertIs(self.model.conds, loaded_conditionals)
        self.assertTrue(self.provider.is_profile_prepared)


class ChatterboxTTSProviderCloneVoiceTest(unittest.TestCase):
    def setUp(self):
        self.voices_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.voices_directory.cleanup)

        self.source_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.source_directory.cleanup)

        self.model = Mock()

        self.provider = ChatterboxTTSProvider(_make_settings())
        self.provider.model = self.model
        self.provider.VOICES_DIR = Path(self.voices_directory.name) / "voices"
        self.provider.prepare_sample_voice = AsyncMock()

    def _make_source_clip(self, seconds: float) -> str:
        source_clip_path = os.path.join(self.source_directory.name, "recording.wav")
        _write_audio_clip(source_clip_path, seconds)
        return source_clip_path

    def _consume_clone_voice(
        self, source_clip_path: str, profile_name: str = PROFILE_NAME
    ):
        async def consume_states():
            return [
                state
                async for state in self.provider.clone_voice(
                    source_clip_path, profile_name
                )
            ]

        return asyncio.run(consume_states())

    def test_clone_voice_raises_when_the_audio_file_does_not_exist(self):
        missing_clip_path = os.path.join(self.source_directory.name, "missing.wav")

        with self.assertRaises(FileNotFoundError):
            self._consume_clone_voice(missing_clip_path)

    def test_clone_voice_raises_when_the_audio_file_is_shorter_than_ten_seconds(self):
        source_clip_path = self._make_source_clip(seconds=5.0)

        with self.assertRaises(ValueError):
            self._consume_clone_voice(source_clip_path)

        self.model.prepare_conditionals.assert_not_called()

    def test_clone_voice_prepares_conditionals_from_the_first_ten_seconds(self):
        source_clip_path = self._make_source_clip(seconds=12.0)
        trimmed_clip_frames = []

        def remember_how_long_the_trimmed_clip_is(wav_fpath, norm_loudness):
            trimmed_clip_frames.append(sf.info(wav_fpath).frames)

        self.model.prepare_conditionals.side_effect = (
            remember_how_long_the_trimmed_clip_is
        )

        self._consume_clone_voice(source_clip_path, f"{PROFILE_NAME}.pt")

        self.assertEqual(trimmed_clip_frames, [10 * CLIP_SAMPLERATE])

    def test_clone_voice_saves_the_profile_with_a_pt_file_extension(self):
        source_clip_path = self._make_source_clip(seconds=12.0)

        self._consume_clone_voice(source_clip_path)

        self.model.conds.save.assert_called_once_with(
            self.provider.VOICES_DIR / f"{PROFILE_NAME}.pt"
        )

    def test_clone_voice_does_not_duplicate_the_pt_file_extension(self):
        source_clip_path = self._make_source_clip(seconds=12.0)

        self._consume_clone_voice(source_clip_path)

        self.model.conds.save.assert_called_once_with(
            self.provider.VOICES_DIR / f"{PROFILE_NAME}.pt"
        )

    def test_clone_voice_removes_the_trimmed_copy_of_the_source_clip(self):
        source_clip_path = self._make_source_clip(seconds=12.0)

        self._consume_clone_voice(source_clip_path)

        trimmed_clip_path = self.provider.VOICES_DIR / "recording.wav"
        self.assertFalse(trimmed_clip_path.exists())

    def test_clone_voice_reports_the_original_error_when_the_trimmed_copy_fails(self):
        source_clip_path = self._make_source_clip(seconds=12.0)

        with patch.object(
            chatterbox_tts_provider.sf, "write", side_effect=OSError("disk full")
        ):
            with self.assertRaises(RuntimeError):
                self._consume_clone_voice(source_clip_path)


class ChatterboxTTSProviderValidationTest(unittest.TestCase):
    def setUp(self):
        self.provider = ChatterboxTTSProvider(_make_settings())

    def test_validate_settings_reports_issue_when_profile_is_empty(self):
        issue = self.provider.validate_settings(_make_settings(profile=""))

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "tts")
        self.assertEqual(issue.field, "profile")

    def test_validate_settings_returns_no_issues_when_profile_is_set(self):
        issue = self.provider.validate_settings(_make_settings())

        self.assertIsNone(issue)


class ChatterboxTTSProviderReloadTest(unittest.TestCase):
    def setUp(self):
        self.model = Mock()

        self.provider = ChatterboxTTSProvider(_make_settings())
        self.provider.model = self.model
        self.provider.is_profile_prepared = True

    def test_reload_provider_keeps_the_model_when_nothing_relevant_changed(self):
        self.provider.reload_provider(_make_settings(volume=0.4))

        self.assertIs(self.provider.model, self.model)
        self.assertTrue(self.provider.is_profile_prepared)

    def test_reload_provider_forgets_the_profile_when_the_profile_changed(self):
        self.provider.reload_provider(_make_settings(profile="aria"))

        self.assertFalse(self.provider.is_profile_prepared)
        self.assertIs(self.provider.model, self.model)

    def test_reload_provider_drops_the_model_when_the_device_changed(self):
        self.provider.reload_provider(_make_settings(device="cpu"))

        self.assertIsNone(self.provider.model)

    def test_reload_provider_drops_the_model_when_the_nano_flag_changed(self):
        self.provider.reload_provider(_make_settings(nano=False))

        self.assertIsNone(self.provider.model)


class ChatterboxTTSProviderGetAvailableDeviceTest(unittest.TestCase):
    def setUp(self):
        self.provider = ChatterboxTTSProvider(_make_settings())

    def test_get_available_device_returns_cuda_when_cuda_is_available(self):
        with patch("torch.cuda.is_available", return_value=True):
            device = self.provider.get_available_device()

        self.assertEqual(device, "cuda")

    def test_get_available_device_returns_cpu_when_cuda_is_unavailable(self):
        with patch("torch.cuda.is_available", return_value=False):
            device = self.provider.get_available_device()

        self.assertEqual(device, "cpu")


class ChatterboxTTSProviderGetAvailableProfilesTest(unittest.TestCase):
    def setUp(self):
        self.voices_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.voices_directory.cleanup)

        self.provider = ChatterboxTTSProvider(_make_settings())
        self.provider.VOICES_DIR = Path(self.voices_directory.name) / "voices"

    def test_get_available_profiles_returns_empty_list_when_voices_directory_does_not_exist(  # noqa: E501
        self,
    ):
        profiles = self.provider.get_available_profiles()

        self.assertEqual(profiles, [])

    def test_get_available_profiles_strips_the_pt_extension_from_pt_files_only(
        self,
    ):
        self.provider.VOICES_DIR.mkdir(parents=True)
        (self.provider.VOICES_DIR / "celeste.pt").touch()
        (self.provider.VOICES_DIR / "aria.pt").touch()
        (self.provider.VOICES_DIR / "notes.txt").touch()
        (self.provider.VOICES_DIR / "subdir").mkdir()

        profiles = self.provider.get_available_profiles()

        self.assertCountEqual(profiles, ["celeste", "aria"])


class FindVoicesDirectoryTest(unittest.TestCase):
    def test_windows_stores_voice_profiles_in_the_local_app_data_directory(self):
        local_app_data = r"C:\Users\cmdr\AppData\Local"

        with patch.dict(os.environ, {"LOCALAPPDATA": local_app_data}):
            voices_directory = chatterbox_tts_provider.find_voices_directory("nt")

        self.assertEqual(
            voices_directory, Path(local_app_data) / "EDCeleste" / "voices"
        )

    def test_other_systems_store_voice_profiles_in_the_home_directory(self):
        with patch.object(Path, "home", return_value=Path("/home/cmdr")):
            voices_directory = chatterbox_tts_provider.find_voices_directory("posix")

        self.assertEqual(
            voices_directory,
            Path("/home/cmdr") / ".local" / "share" / "EDCeleste" / "voices",
        )


class AddPtFileExtensionIfMissingTest(unittest.TestCase):
    def test_appends_pt_extension_when_missing(self):
        result = chatterbox_tts_provider.add_pt_file_extension_if_missing("celeste")

        self.assertEqual(result, "celeste.pt")

    def test_leaves_the_file_name_unchanged_when_pt_extension_is_already_present(self):
        result = chatterbox_tts_provider.add_pt_file_extension_if_missing("celeste.pt")

        self.assertEqual(result, "celeste.pt")


if __name__ == "__main__":
    unittest.main()
