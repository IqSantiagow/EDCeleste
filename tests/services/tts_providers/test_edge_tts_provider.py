import unittest
from unittest.mock import AsyncMock, patch

import numpy as np

from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    EdgeParamsModel,
)
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider

VOICE = "en-US-AriaNeural"


def _make_edge_params(voice: str = VOICE) -> EdgeParamsModel:
    return EdgeParamsModel(type="edge", voice=voice)


def _make_chatterbox_params() -> ChatterboxParamsModel:
    return ChatterboxParamsModel(type="chatterbox", profile="celeste")


class EdgeTTSProviderSynthesizeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        communicate_patcher = patch(
            "edceleste.services.tts_providers.edge_tts_provider.edge_tts.Communicate"
        )
        sf_read_patcher = patch(
            "edceleste.services.tts_providers.edge_tts_provider.sf.read"
        )
        os_remove_patcher = patch(
            "edceleste.services.tts_providers.edge_tts_provider.os.remove"
        )

        self.mock_communicate_cls = communicate_patcher.start()
        self.mock_sf_read = sf_read_patcher.start()
        self.mock_os_remove = os_remove_patcher.start()

        self.addCleanup(communicate_patcher.stop)
        self.addCleanup(sf_read_patcher.stop)
        self.addCleanup(os_remove_patcher.stop)

        self.mock_communicate = self.mock_communicate_cls.return_value
        self.mock_communicate.save = AsyncMock()

        self.audio_data = np.array([0.1, 0.2, 0.3])
        self.samplerate = 24000
        self.mock_sf_read.return_value = (self.audio_data, self.samplerate)

        self.provider = EdgeTTSProvider()

    async def test_synthesize_returns_samples_and_sample_rate(self):
        samples, sample_rate = await self.provider.synthesize(
            "Hello Commander", _make_edge_params()
        )

        np.testing.assert_allclose(samples, self.audio_data)
        self.assertEqual(sample_rate, self.samplerate)

    async def test_synthesize_saves_audio_using_the_voice_from_params(self):
        await self.provider.synthesize("Hello Commander", _make_edge_params())

        self.mock_communicate_cls.assert_called_once_with(
            "Hello Commander", voice=VOICE
        )
        self.mock_communicate.save.assert_awaited_once_with("output.mp3")

    async def test_synthesize_reads_the_saved_file(self):
        await self.provider.synthesize("Hello Commander", _make_edge_params())

        self.mock_sf_read.assert_called_once_with("output.mp3")

    async def test_synthesize_removes_temporary_file_after_reading_it(self):
        await self.provider.synthesize("Hello Commander", _make_edge_params())

        self.mock_os_remove.assert_called_once_with("output.mp3")

    async def test_synthesize_ignores_the_profile_path(self):
        samples, sample_rate = await self.provider.synthesize(
            "Hello Commander", _make_edge_params(), profile_path=None
        )

        np.testing.assert_allclose(samples, self.audio_data)
        self.assertEqual(sample_rate, self.samplerate)

    async def test_synthesize_rejects_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            await self.provider.synthesize("Hello Commander", _make_chatterbox_params())

        self.mock_communicate_cls.assert_not_called()

    async def test_synthesize_propagates_error_when_saving_audio_fails(self):
        self.mock_communicate.save.side_effect = RuntimeError("network down")

        with self.assertRaises(RuntimeError):
            await self.provider.synthesize("Hello Commander", _make_edge_params())

        self.mock_sf_read.assert_not_called()
        self.mock_os_remove.assert_not_called()


class EdgeTTSProviderValidateParamsTest(unittest.TestCase):
    def setUp(self):
        self.provider = EdgeTTSProvider()

    def test_validate_params_reports_issue_when_voice_missing(self):
        issue = self.provider.validate_params(_make_edge_params(voice=""))

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "tts")
        self.assertEqual(issue.field, "voice")

    def test_validate_params_returns_none_when_voice_is_set(self):
        issue = self.provider.validate_params(_make_edge_params())

        self.assertIsNone(issue)

    def test_validate_params_rejects_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            self.provider.validate_params(_make_chatterbox_params())
