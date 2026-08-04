import unittest
from unittest.mock import AsyncMock, Mock, patch

from services.llm_service import SYSTEM_PROMPT
from services.models.settings_model import (
    PathModel,
    SettingsModel,
    TTSModel,
    LLMModel,
)
from services.settings_service import SettingsService

from services.event_bus import EventBus
from services.tts_service import TTSEvent, TTSService

VOICE = "en-US-AriaNeural"


def _make_settings(api_key: str) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice=VOICE, volume=1.0),
        llm=LLMModel(api_key=api_key, system_prompt=SYSTEM_PROMPT, user_prompt=""),
    )


class TTSServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        communicate_patcher = patch("services.tts_service.edge_tts.Communicate")
        sf_read_patcher = patch("services.tts_service.sf.read")
        sd_play_patcher = patch("services.tts_service.sd.play")
        os_remove_patcher = patch("services.tts_service.os.remove")

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

        self.audio_data = [0.1, 0.2, 0.3]
        self.samplerate = 24000
        self.mock_sf_read.return_value = (self.audio_data, self.samplerate)

        self.settings_handler = Mock(spec=SettingsService)

        self.settings_handler.get_settings.return_value = _make_settings(
            api_key="sk-ant-test"
        )

        self.service = TTSService(
            voice=VOICE, event_bus=EventBus(), settings_handler=self.settings_handler
        )

    async def test_event_bus_publish_of_tts_event_triggers_synthesize(self):
        event_bus = EventBus()
        service = TTSService(
            voice=VOICE, event_bus=event_bus, settings_handler=self.settings_handler
        )
        service.synthesize = AsyncMock()

        await event_bus.publish(TTSEvent("Hello Commander"))

        service.synthesize.assert_called_once_with("Hello Commander")

    async def test_handle_tts_request_calls_synthesize_with_event_text(self):
        self.service.synthesize = AsyncMock()

        await self.service.handle_tts_request(TTSEvent("Fuel level low"))

        self.service.synthesize.assert_called_once_with("Fuel level low")

    async def test_synthesize_saves_audio_via_edge_tts_using_configured_voice(self):
        await self.service.synthesize("Hello Commander")

        self.mock_communicate_cls.assert_called_once_with(
            "Hello Commander", voice=VOICE
        )
        self.mock_communicate.save.assert_awaited_once_with("output.mp3")

    async def test_synthesize_plays_audio_data_read_from_saved_file(self):
        await self.service.synthesize("Hello Commander")

        self.mock_sf_read.assert_called_once_with("output.mp3")
        self.mock_sd_play.assert_called_once_with(self.audio_data, self.samplerate)

    async def test_synthesize_removes_temporary_file_after_playback(self):
        await self.service.synthesize("Hello Commander")

        self.mock_os_remove.assert_called_once_with("output.mp3")

    async def test_synthesize_propagates_error_when_edge_tts_save_fails(self):
        self.mock_communicate.save.side_effect = RuntimeError("network down")

        with self.assertRaises(RuntimeError):
            await self.service.synthesize("Hello Commander")

        self.mock_sd_play.assert_not_called()
        self.mock_os_remove.assert_not_called()

    def test_validate_settings_reports_issue_when_voice_missing(self):
        new_settings = _make_settings(api_key="sk-ant-test")
        new_settings.tts.voice = ""

        issue = self.service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.field, "voice")

    def test_validate_settings_returns_no_issues_when_voice_present(self):
        new_settings = _make_settings(api_key="sk-ant-test")

        issue = self.service.validate_settings(new_settings)

        self.assertIsNone(issue)

    def test_reload_service_changes_voice_from_settings_handler(self):
        new_settings = _make_settings(api_key="sk-ant-test")
        new_settings.tts.voice = "en-US-GuyNeural"
        self.settings_handler.get_settings.return_value = new_settings

        self.service.reload_service()

        self.assertEqual(self.service.voice, "en-US-GuyNeural")


if __name__ == "__main__":
    unittest.main()
