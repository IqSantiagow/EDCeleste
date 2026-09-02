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


def _write_audio_clip(
    path: str, seconds: float, amplitude: float = 0.0, channels: int = 1
) -> None:
    frame_count = int(seconds * CLIP_SAMPLERATE)
    shape = frame_count if channels == 1 else (frame_count, channels)
    samples = np.full(shape, amplitude, dtype="float32")
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


class ChatterboxTTSProviderPrepareSampleVoiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_tts_turbo_module = _install_fake_chatterbox_module(self)

        self.voices_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.voices_directory.cleanup)

        self.generated_samples = np.array([0.1, 0.2, 0.3])
        self.model = _make_model_mock(self.generated_samples)
        self.model.device = "cpu"
        self.loaded_conditionals = Mock()
        self.fake_tts_turbo_module.Conditionals.load.return_value = (
            self.loaded_conditionals
        )

        self.provider = ChatterboxTTSProvider(_make_settings())
        self.provider.model = self.model
        self.provider.VOICES_DIR = Path(self.voices_directory.name)

        profile_path = Path(self.voices_directory.name) / f"{PROFILE_NAME}.pt"
        profile_path.touch()

    async def test_reloads_this_profiles_conditionals_before_generating(self):
        # Guards against the model.conds swap-out bug: something else in the
        # app (background narration) could have loaded a different profile's
        # conditionals onto the model in the meantime.
        await self.provider.prepare_sample_voice(PROFILE_NAME)

        profile_path = Path(self.voices_directory.name) / f"{PROFILE_NAME}.pt"
        self.fake_tts_turbo_module.Conditionals.load.assert_called_once_with(
            profile_path, "cpu"
        )
        self.assertIs(self.model.conds, self.loaded_conditionals)

    async def test_uses_the_default_text_when_none_is_given(self):
        await self.provider.prepare_sample_voice(PROFILE_NAME)

        self.model.generate.assert_called_once_with(
            text=chatterbox_tts_provider.DEFAULT_VOICE_SAMPLE_TEXT,
            norm_loudness=False,
            exaggeration=self.provider.provider_settings.exaggeration,
            cfg_weight=self.provider.provider_settings.cfg_weight,
        )

    async def test_uses_the_given_text_instead_of_the_default(self):
        await self.provider.prepare_sample_voice(PROFILE_NAME, text="Ahoy Commander.")

        self.model.generate.assert_called_once_with(
            text="Ahoy Commander.",
            norm_loudness=False,
            exaggeration=self.provider.provider_settings.exaggeration,
            cfg_weight=self.provider.provider_settings.cfg_weight,
        )

    async def test_writes_the_generated_sample_to_disk(self):
        await self.provider.prepare_sample_voice(PROFILE_NAME)

        sample_path = Path(self.voices_directory.name) / f"{PROFILE_NAME}_sample.wav"
        self.assertTrue(sample_path.exists())


class ChatterboxTTSProviderPreviewVoiceSampleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_sounddevice_module = MagicMock()
        sounddevice_patcher = patch.dict(
            sys.modules, {"sounddevice": self.fake_sounddevice_module}
        )
        sounddevice_patcher.start()
        self.addCleanup(sounddevice_patcher.stop)
        self.mock_sd_play = self.fake_sounddevice_module.play

        self.fake_tts_turbo_module = _install_fake_chatterbox_module(self)

        self.voices_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.voices_directory.cleanup)

        self.generated_samples = np.array([0.1, 0.2, 0.3])
        self.model = _make_model_mock(self.generated_samples)
        self.model.device = "cpu"
        self.loaded_conditionals = Mock()
        self.fake_tts_turbo_module.Conditionals.load.return_value = (
            self.loaded_conditionals
        )

        self.provider = ChatterboxTTSProvider(_make_settings())
        self.provider.model = self.model
        self.provider.VOICES_DIR = Path(self.voices_directory.name)

        profile_path = Path(self.voices_directory.name) / f"{PROFILE_NAME}.pt"
        profile_path.touch()

    async def test_reloads_this_profiles_conditionals_before_generating(self):
        await self.provider.preview_voice_sample(PROFILE_NAME, "Ahoy Commander.")

        profile_path = Path(self.voices_directory.name) / f"{PROFILE_NAME}.pt"
        self.fake_tts_turbo_module.Conditionals.load.assert_called_once_with(
            profile_path, "cpu"
        )
        self.assertIs(self.model.conds, self.loaded_conditionals)

    async def test_generates_and_plays_the_given_text(self):
        await self.provider.preview_voice_sample(PROFILE_NAME, "Ahoy Commander.")

        self.model.generate.assert_called_once_with(
            text="Ahoy Commander.",
            norm_loudness=False,
            exaggeration=self.provider.provider_settings.exaggeration,
            cfg_weight=self.provider.provider_settings.cfg_weight,
        )
        played_samples, played_samplerate = self.mock_sd_play.call_args.args
        np.testing.assert_allclose(played_samples, self.generated_samples)
        self.assertEqual(played_samplerate, self.model.sr)

    async def test_does_not_write_anything_to_disk(self):
        # This is the whole point of preview_voice_sample vs
        # prepare_sample_voice - trying out text must never overwrite the
        # profile's saved demo sample.
        await self.provider.preview_voice_sample(PROFILE_NAME, "Ahoy Commander.")

        sample_path = Path(self.voices_directory.name) / f"{PROFILE_NAME}_sample.wav"
        self.assertFalse(sample_path.exists())


class ChatterboxTTSProviderRenameProfileTest(unittest.TestCase):
    def setUp(self):
        self.voices_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.voices_directory.cleanup)

        self.provider = ChatterboxTTSProvider(_make_settings())
        self.provider.VOICES_DIR = Path(self.voices_directory.name)

    def _touch(self, file_name: str) -> Path:
        path = Path(self.voices_directory.name) / file_name
        path.touch()
        return path

    def test_renames_both_the_pt_file_and_the_sample(self):
        self._touch("celeste.pt")
        self._touch("celeste_sample.wav")

        self.provider.rename_profile("celeste", "celeste-v2")

        voices_dir = Path(self.voices_directory.name)
        self.assertTrue((voices_dir / "celeste-v2.pt").exists())
        self.assertTrue((voices_dir / "celeste-v2_sample.wav").exists())
        self.assertFalse((voices_dir / "celeste.pt").exists())
        self.assertFalse((voices_dir / "celeste_sample.wav").exists())

    def test_renames_the_pt_file_even_when_there_is_no_sample_yet(self):
        self._touch("celeste.pt")

        self.provider.rename_profile("celeste", "celeste-v2")

        voices_dir = Path(self.voices_directory.name)
        self.assertTrue((voices_dir / "celeste-v2.pt").exists())

    def test_raises_and_leaves_files_untouched_when_the_new_name_is_taken(self):
        self._touch("celeste.pt")
        self._touch("celeste-v2.pt")

        with self.assertRaises(FileExistsError):
            self.provider.rename_profile("celeste", "celeste-v2")

        voices_dir = Path(self.voices_directory.name)
        self.assertTrue((voices_dir / "celeste.pt").exists())

    @unittest.skipUnless(
        os.name == "nt",
        "case-insensitive filename collisions only happen on Windows",
    )
    def test_raises_when_the_new_name_only_differs_by_case(self):
        # Windows filesystems are case-insensitive, so "Celeste" and
        # "celeste" would otherwise silently collide on disk.
        self._touch("celeste.pt")
        self._touch("celeste-v2.pt")

        with self.assertRaises(FileExistsError):
            self.provider.rename_profile("celeste", "CELESTE-V2")


class CalculatePeakDbfsTest(unittest.TestCase):
    def test_returns_zero_dbfs_for_a_full_scale_signal(self):
        peak_dbfs = chatterbox_tts_provider.calculate_peak_dbfs(
            np.array([1.0, -0.5, 0.2])
        )

        self.assertAlmostEqual(peak_dbfs, 0.0, places=5)

    def test_returns_the_silence_floor_for_an_all_zero_signal(self):
        peak_dbfs = chatterbox_tts_provider.calculate_peak_dbfs(np.zeros(100))

        self.assertEqual(peak_dbfs, chatterbox_tts_provider.SILENCE_FLOOR_DBFS)

    def test_returns_a_lower_value_for_a_quieter_signal(self):
        peak_dbfs = chatterbox_tts_provider.calculate_peak_dbfs(np.array([0.1, -0.1]))

        self.assertAlmostEqual(peak_dbfs, -20.0, places=5)


class CalculateNoiseFloorDbfsTest(unittest.TestCase):
    def test_picks_the_quietest_window_in_the_clip(self):
        loud_window = np.full(10, 1.0)
        quiet_window = np.full(10, 0.01)
        samples = np.concatenate([loud_window, quiet_window])

        noise_floor_dbfs = chatterbox_tts_provider.calculate_noise_floor_dbfs(
            samples, sample_rate=100
        )

        self.assertAlmostEqual(noise_floor_dbfs, -40.0, places=5)

    def test_returns_the_silence_floor_for_an_all_zero_signal(self):
        noise_floor_dbfs = chatterbox_tts_provider.calculate_noise_floor_dbfs(
            np.zeros(1000), sample_rate=100
        )

        self.assertEqual(noise_floor_dbfs, chatterbox_tts_provider.SILENCE_FLOOR_DBFS)


class CalculateWaveformEnvelopeTest(unittest.TestCase):
    def test_returns_one_peak_amplitude_value_per_window(self):
        first_window = np.full(10, 0.2)
        second_window = np.full(10, 0.8)
        samples = np.concatenate([first_window, second_window])

        envelope = chatterbox_tts_provider.calculate_waveform_envelope(
            samples, sample_rate=100, window_seconds=0.1
        )

        self.assertEqual(len(envelope), 2)
        self.assertAlmostEqual(envelope[0], 0.2, places=5)
        self.assertAlmostEqual(envelope[1], 0.8, places=5)


class ChatterboxTTSProviderAnalyzeSampleTest(unittest.TestCase):
    def setUp(self):
        self.source_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.source_directory.cleanup)

        self.provider = ChatterboxTTSProvider(_make_settings())

    def _clip_path(self, name: str = "reference.wav") -> str:
        return os.path.join(self.source_directory.name, name)

    def test_reports_duration_samplerate_and_mono_channel_count(self):
        clip_path = self._clip_path()
        _write_audio_clip(clip_path, seconds=12.0)

        analysis = self.provider.perform_sample_voice_analysis_and_validate(clip_path)

        self.assertAlmostEqual(analysis["duration_seconds"], 12.0, places=2)
        self.assertEqual(analysis["sample_rate"], CLIP_SAMPLERATE)
        self.assertEqual(analysis["channels"], 1)
        self.assertTrue(analysis["is_mono"])
        self.assertEqual(analysis["file_name"], "reference.wav")

    def test_reports_stereo_files_as_not_mono(self):
        clip_path = self._clip_path()
        _write_audio_clip(clip_path, seconds=12.0, channels=2)

        analysis = self.provider.perform_sample_voice_analysis_and_validate(clip_path)

        self.assertEqual(analysis["channels"], 2)
        self.assertFalse(analysis["is_mono"])

    def test_is_valid_when_the_clip_meets_the_minimum_length(self):
        clip_path = self._clip_path()
        _write_audio_clip(clip_path, seconds=12.0)

        analysis = self.provider.perform_sample_voice_analysis_and_validate(clip_path)

        self.assertTrue(analysis["is_valid"])
        self.assertIsNone(analysis["validation_error_message"])

    def test_is_invalid_when_the_clip_is_shorter_than_the_minimum_length(self):
        clip_path = self._clip_path()
        _write_audio_clip(clip_path, seconds=5.0)

        analysis = self.provider.perform_sample_voice_analysis_and_validate(clip_path)

        self.assertFalse(analysis["is_valid"])
        self.assertIn("Too short", analysis["validation_error_message"])

    def test_reports_silence_as_the_dbfs_floor_with_no_clipping(self):
        clip_path = self._clip_path()
        _write_audio_clip(clip_path, seconds=12.0)

        analysis = self.provider.perform_sample_voice_analysis_and_validate(clip_path)

        self.assertEqual(
            analysis["peak_dbfs"], chatterbox_tts_provider.SILENCE_FLOOR_DBFS
        )
        self.assertEqual(
            analysis["noise_floor_dbfs"], chatterbox_tts_provider.SILENCE_FLOOR_DBFS
        )
        self.assertFalse(analysis["has_clipping"])


class ChatterboxTTSProviderPlayAudioFileTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_sounddevice_module = MagicMock()
        sounddevice_patcher = patch.dict(
            sys.modules, {"sounddevice": self.fake_sounddevice_module}
        )
        sounddevice_patcher.start()
        self.addCleanup(sounddevice_patcher.stop)
        self.mock_sd_play = self.fake_sounddevice_module.play

        self.source_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.source_directory.cleanup)

        self.provider = ChatterboxTTSProvider(_make_settings(volume=0.5))

    async def test_play_audio_file_plays_the_given_file_scaled_by_volume(self):
        clip_path = os.path.join(self.source_directory.name, "reference.wav")
        _write_audio_clip(clip_path, seconds=1.0, amplitude=0.4)

        await self.provider.play_audio_file(clip_path)

        played_samples, played_samplerate = self.mock_sd_play.call_args.args
        self.assertEqual(played_samplerate, CLIP_SAMPLERATE)
        np.testing.assert_allclose(played_samples, played_samples[0], atol=1e-3)

    async def test_play_sample_voice_raises_when_the_profile_sample_is_missing(self):
        self.provider.VOICES_DIR = Path(self.source_directory.name)

        with self.assertRaises(FileNotFoundError):
            await self.provider.play_sample_voice("missing-profile")

    async def test_play_sample_voice_plays_the_saved_profile_sample(self):
        self.provider.VOICES_DIR = Path(self.source_directory.name)
        sample_path = self.provider.VOICES_DIR / "celeste_sample.wav"
        _write_audio_clip(str(sample_path), seconds=1.0, amplitude=0.4)

        await self.provider.play_sample_voice("celeste")

        self.mock_sd_play.assert_called_once()


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
