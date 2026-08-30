import unittest
from unittest.mock import AsyncMock, patch

import numpy as np

from edceleste.services.models.settings_model import (
    EdgeTTSProviderModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider

VOICE = "en-US-AriaNeural"


def _make_settings(voice: str = VOICE, volume: float = 1.0) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(
            provider=EdgeTTSProviderModel(type="edge", voice=voice),
            volume=volume,
        ),
        llm=LLMModel(system_prompt="sp", user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


class EdgeTTSProviderTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        communicate_patcher = patch(
            "edceleste.services.tts_providers.edge_tts_provider.edge_tts.Communicate"
        )
        sf_read_patcher = patch(
            "edceleste.services.tts_providers.edge_tts_provider.sf.read"
        )
        sd_play_patcher = patch(
            "edceleste.services.tts_providers.edge_tts_provider.sd.play"
        )
        os_remove_patcher = patch(
            "edceleste.services.tts_providers.edge_tts_provider.os.remove"
        )

        self.mock_communicate_cls = communicate_patcher.start()
        self.mock_sf_read = sf_read_patcher.start()
        self.mock_sd_play = sd_play_patcher.start()
        self.mock_os_remove = os_remove_patcher.start()

        self.addCleanup(communicate_patcher.stop)
        self.addCleanup(sf_read_patcher.stop)
        self.addCleanup(sd_play_patcher.stop)
        self.addCleanup(os_remove_patcher.stop)

        self.mock_communicate = self.mock_communicate_cls.return_value
        self.mock_communicate.save = AsyncMock()

        self.audio_data = np.array([0.1, 0.2, 0.3])
        self.samplerate = 24000
        self.mock_sf_read.return_value = (self.audio_data, self.samplerate)

        self.provider = EdgeTTSProvider(_make_settings())

    async def test_synthesize_saves_audio_using_the_configured_voice(self):
        await self.provider.synthesize("Hello Commander")

        self.mock_communicate_cls.assert_called_once_with(
            "Hello Commander", voice=VOICE
        )
        self.mock_communicate.save.assert_awaited_once_with("output.mp3")

    async def test_synthesize_plays_audio_data_read_from_saved_file(self):
        await self.provider.synthesize("Hello Commander")

        self.mock_sf_read.assert_called_once_with("output.mp3")
        played_samples, played_samplerate = self.mock_sd_play.call_args.args
        np.testing.assert_allclose(played_samples, self.audio_data)
        self.assertEqual(played_samplerate, self.samplerate)

    async def test_synthesize_scales_played_audio_by_configured_volume(self):
        provider = EdgeTTSProvider(_make_settings(volume=0.5))

        await provider.synthesize("Hello Commander")

        played_samples, _ = self.mock_sd_play.call_args.args
        np.testing.assert_allclose(played_samples, self.audio_data * 0.5)

    async def test_synthesize_removes_temporary_file_after_playback(self):
        await self.provider.synthesize("Hello Commander")

        self.mock_os_remove.assert_called_once_with("output.mp3")

    async def test_synthesize_propagates_error_when_saving_audio_fails(self):
        self.mock_communicate.save.side_effect = RuntimeError("network down")

        with self.assertRaises(RuntimeError):
            await self.provider.synthesize("Hello Commander")

        self.mock_sd_play.assert_not_called()
        self.mock_os_remove.assert_not_called()

    def test_validate_settings_reports_issue_when_voice_missing(self):
        new_settings = _make_settings(voice="")

        issue = self.provider.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "tts")
        self.assertEqual(issue.field, "voice")

    def test_validate_settings_returns_no_issues_when_voice_present(self):
        issue = self.provider.validate_settings(_make_settings())

        self.assertIsNone(issue)


if __name__ == "__main__":
    unittest.main()
