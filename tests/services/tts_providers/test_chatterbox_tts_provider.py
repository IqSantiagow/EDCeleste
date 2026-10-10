import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import torch  # noqa: F401  (kept in sys.modules while chatterbox is faked)

from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    EdgeParamsModel,
)
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)

PROFILE_NAME = "celeste"


def _make_chatterbox_params(
    profile: str = PROFILE_NAME,
    device: str = "cpu",
    nano: bool = True,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
) -> ChatterboxParamsModel:
    return ChatterboxParamsModel(
        type="chatterbox",
        profile=profile,
        device=device,
        nano=nano,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
    )


def _make_edge_params() -> EdgeParamsModel:
    return EdgeParamsModel(type="edge", voice="en-US-AriaNeural")


def _make_model_mock(generated_samples: np.ndarray) -> Mock:
    generated_waveform = Mock()
    generated_waveform.squeeze.return_value.cpu.return_value.numpy.return_value = (
        generated_samples
    )

    model = Mock()
    model.sr = 24000
    model.device = "cpu"
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


class ChatterboxTTSProviderSynthesizeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_tts_turbo_module = _install_fake_chatterbox_module(self)
        self.from_pretrained = (
            self.fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained
        )
        self.conditionals_load = self.fake_tts_turbo_module.Conditionals.load

        self.generated_samples = np.array([0.1, 0.2, 0.3])
        self.model = _make_model_mock(self.generated_samples)
        self.from_pretrained.return_value = self.model

        self.profiles_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.profiles_directory.cleanup)
        self.profile_path = self._make_profile_file("celeste.pt")

        self.provider = ChatterboxTTSProvider()

    def _make_profile_file(self, file_name: str) -> Path:
        profile_path = Path(self.profiles_directory.name) / file_name
        profile_path.touch()
        return profile_path

    async def test_synthesize_returns_generated_samples_and_model_sample_rate(self):
        samples, sample_rate = await self.provider.synthesize(
            "Hello Commander", _make_chatterbox_params(), self.profile_path
        )

        np.testing.assert_allclose(samples, self.generated_samples)
        self.assertEqual(sample_rate, 24000)

    async def test_synthesize_passes_exaggeration_and_cfg_weight_to_the_model(self):
        params = _make_chatterbox_params(exaggeration=0.8, cfg_weight=0.3)

        await self.provider.synthesize("Hello Commander", params, self.profile_path)

        self.model.generate.assert_called_once_with(
            text="Hello Commander",
            norm_loudness=False,
            exaggeration=0.8,
            cfg_weight=0.3,
        )

    async def test_synthesize_loads_the_model_once_for_the_same_params(self):
        params = _make_chatterbox_params()

        await self.provider.synthesize("One", params, self.profile_path)
        await self.provider.synthesize("Two", params, self.profile_path)

        self.from_pretrained.assert_called_once_with(device="cpu", nano=True)

    async def test_synthesize_loads_the_model_again_when_device_changes(self):
        await self.provider.synthesize(
            "One", _make_chatterbox_params(device="cpu"), self.profile_path
        )
        await self.provider.synthesize(
            "Two", _make_chatterbox_params(device="cuda"), self.profile_path
        )

        self.assertEqual(self.from_pretrained.call_count, 2)
        self.from_pretrained.assert_called_with(device="cuda", nano=True)

    async def test_synthesize_loads_the_model_again_when_nano_changes(self):
        await self.provider.synthesize(
            "One", _make_chatterbox_params(nano=True), self.profile_path
        )
        await self.provider.synthesize(
            "Two", _make_chatterbox_params(nano=False), self.profile_path
        )

        self.assertEqual(self.from_pretrained.call_count, 2)
        self.from_pretrained.assert_called_with(device="cpu", nano=False)

    async def test_synthesize_turns_auto_device_into_the_available_one(self):
        with patch("torch.cuda.is_available", return_value=True):
            await self.provider.synthesize(
                "One", _make_chatterbox_params(device="auto"), self.profile_path
            )

        self.from_pretrained.assert_called_once_with(device="cuda", nano=True)

    async def test_synthesize_loads_the_profile_into_the_model(self):
        loaded_conditionals = Mock()
        self.conditionals_load.return_value = loaded_conditionals

        await self.provider.synthesize(
            "Hello", _make_chatterbox_params(), self.profile_path
        )

        self.conditionals_load.assert_called_once_with(self.profile_path, "cpu")
        self.assertIs(self.model.conds, loaded_conditionals)
        self.assertEqual(self.provider.loaded_profile_path, self.profile_path)

    async def test_synthesize_skips_loading_the_same_profile_again(self):
        params = _make_chatterbox_params()

        await self.provider.synthesize("One", params, self.profile_path)
        await self.provider.synthesize("Two", params, self.profile_path)

        self.conditionals_load.assert_called_once()

    async def test_synthesize_loads_the_profile_again_when_it_differs(self):
        other_profile_path = self._make_profile_file("other.pt")
        params = _make_chatterbox_params()

        await self.provider.synthesize("One", params, self.profile_path)
        await self.provider.synthesize("Two", params, other_profile_path)

        self.assertEqual(self.conditionals_load.call_count, 2)
        self.conditionals_load.assert_called_with(other_profile_path, "cpu")
        self.assertEqual(self.provider.loaded_profile_path, other_profile_path)

    async def test_synthesize_loads_the_profile_again_after_the_model_is_reloaded(
        self,
    ):
        await self.provider.synthesize(
            "One", _make_chatterbox_params(device="cpu"), self.profile_path
        )
        await self.provider.synthesize(
            "Two", _make_chatterbox_params(device="cuda"), self.profile_path
        )

        self.assertEqual(self.conditionals_load.call_count, 2)

    async def test_synthesize_raises_when_the_profile_file_does_not_exist(self):
        missing_profile_path = Path(self.profiles_directory.name) / "missing.pt"

        with self.assertRaises(FileNotFoundError):
            await self.provider.synthesize(
                "Hello", _make_chatterbox_params(), missing_profile_path
            )

        self.model.generate.assert_not_called()
        self.assertIsNone(self.provider.loaded_profile_path)

    async def test_synthesize_raises_when_profile_path_is_none(self):
        with self.assertRaises(ValueError):
            await self.provider.synthesize("Hello", _make_chatterbox_params(), None)

        self.from_pretrained.assert_not_called()

    async def test_synthesize_rejects_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            await self.provider.synthesize(
                "Hello", _make_edge_params(), self.profile_path
            )

        self.from_pretrained.assert_not_called()


class ChatterboxTTSProviderCreateVoiceProfileTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_tts_turbo_module = _install_fake_chatterbox_module(self)
        self.from_pretrained = (
            self.fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained
        )

        self.model = _make_model_mock(np.array([0.1]))
        self.from_pretrained.return_value = self.model

        self.provider = ChatterboxTTSProvider()
        self.profile_path = Path("voices") / "celeste.pt"

    async def test_create_voice_profile_prepares_conditionals_from_the_reference(self):
        await self.provider.create_voice_profile(
            "reference.wav", self.profile_path, _make_chatterbox_params()
        )

        self.model.prepare_conditionals.assert_called_once_with(
            wav_fpath="reference.wav", norm_loudness=False
        )

    async def test_create_voice_profile_saves_conditionals_to_the_profile_path(self):
        await self.provider.create_voice_profile(
            "reference.wav", self.profile_path, _make_chatterbox_params()
        )

        self.model.conds.save.assert_called_once_with(self.profile_path)

    async def test_create_voice_profile_clears_the_loaded_profile_path(self):
        self.provider.loaded_profile_path = Path("voices") / "old.pt"

        await self.provider.create_voice_profile(
            "reference.wav", self.profile_path, _make_chatterbox_params()
        )

        self.assertIsNone(self.provider.loaded_profile_path)

    async def test_create_voice_profile_loads_the_model_with_the_given_params(self):
        await self.provider.create_voice_profile(
            "reference.wav", self.profile_path, _make_chatterbox_params(nano=False)
        )

        self.from_pretrained.assert_called_once_with(device="cpu", nano=False)

    async def test_create_voice_profile_rejects_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            await self.provider.create_voice_profile(
                "reference.wav", self.profile_path, _make_edge_params()
            )

        self.model.prepare_conditionals.assert_not_called()


class ChatterboxTTSProviderValidateParamsTest(unittest.TestCase):
    def setUp(self):
        self.provider = ChatterboxTTSProvider()

    def test_validate_params_reports_issue_when_profile_is_empty(self):
        issue = self.provider.validate_params(_make_chatterbox_params(profile=""))

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "tts")
        self.assertEqual(issue.field, "profile")

    def test_validate_params_returns_none_when_profile_is_set(self):
        issue = self.provider.validate_params(_make_chatterbox_params())

        self.assertIsNone(issue)

    def test_validate_params_rejects_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            self.provider.validate_params(_make_edge_params())


class ChatterboxTTSProviderAvailableDeviceTest(unittest.TestCase):
    def setUp(self):
        self.provider = ChatterboxTTSProvider()

    def test_get_available_device_returns_cuda_when_a_gpu_is_visible(self):
        with patch("torch.cuda.is_available", return_value=True):
            self.assertEqual(self.provider.get_available_device(), "cuda")

    def test_get_available_device_returns_cpu_without_a_gpu(self):
        with patch("torch.cuda.is_available", return_value=False):
            self.assertEqual(self.provider.get_available_device(), "cpu")

    def test_provider_starts_without_a_loaded_model(self):
        self.assertIsNone(self.provider.model)
        self.assertIsNone(self.provider.loaded_profile_path)
