import unittest
from unittest.mock import AsyncMock, Mock, patch

from edceleste.services.llm_service import SYSTEM_PROMPT
from edceleste.services.models.settings_model import (
    ChatterboxTTSProviderModel,
    EdgeTTSProviderModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
    LLMModel,
)
from edceleste.services.settings_service import SettingsService

from edceleste.services.event_bus import EventBus
from edceleste.services.exceptions.voice_cloning_exception import (
    VoiceCloningException,
)
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider
from edceleste.services.tts_service import TTSEvent, TTSService

VOICE = "en-US-AriaNeural"


def _make_settings(api_key: str, provider=None) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(
            provider=provider or EdgeTTSProviderModel(type="edge", voice=VOICE),
            volume=1.0,
        ),
        llm=LLMModel(api_key=api_key, system_prompt=SYSTEM_PROMPT, user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


def _make_chatterbox_provider(profile: str = "celeste") -> ChatterboxTTSProviderModel:
    return ChatterboxTTSProviderModel(type="chatterbox", profile=profile)


class TTSServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings_handler = Mock(spec=SettingsService)

        self.settings_handler.get_settings.return_value = _make_settings(
            api_key="sk-ant-test"
        )

        self.service = TTSService(
            event_bus=EventBus(), settings_handler=self.settings_handler
        )

    async def test_event_bus_publish_of_tts_event_triggers_synthesize(self):
        event_bus = EventBus()
        service = TTSService(
            event_bus=event_bus, settings_handler=self.settings_handler
        )
        service.synthesize = AsyncMock()

        await event_bus.publish(TTSEvent("Hello Commander"))

        service.synthesize.assert_called_once_with("Hello Commander")

    async def test_handle_tts_request_calls_synthesize_with_event_text(self):
        self.service.synthesize = AsyncMock()

        await self.service.handle_tts_request(TTSEvent("Fuel level low"))

        self.service.synthesize.assert_called_once_with("Fuel level low")

    def test_edge_provider_is_built_for_the_edge_provider_type(self):
        self.assertIsInstance(self.service.provider, EdgeTTSProvider)

    def test_chatterbox_provider_is_built_for_the_chatterbox_provider_type(self):
        self.settings_handler.get_settings.return_value = _make_settings(
            api_key="sk-ant-test", provider=_make_chatterbox_provider()
        )

        self.service.reload_service()

        self.assertIsInstance(self.service.provider, ChatterboxTTSProvider)

    async def test_synthesize_delegates_to_the_active_provider(self):
        self.service.provider = Mock()
        self.service.provider.synthesize = AsyncMock()

        await self.service.synthesize("Hello Commander")

        self.service.provider.synthesize.assert_awaited_once_with("Hello Commander")

    async def test_synthesize_propagates_error_raised_by_the_provider(self):
        self.service.provider = Mock()
        self.service.provider.synthesize = AsyncMock(
            side_effect=RuntimeError("network down")
        )

        with self.assertRaises(RuntimeError):
            await self.service.synthesize("Hello Commander")

    def test_validate_settings_reports_issue_when_edge_voice_missing(self):
        new_settings = _make_settings(api_key="sk-ant-test")
        new_settings.tts.provider.voice = ""

        issue = self.service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "tts")
        self.assertEqual(issue.field, "voice")

    def test_validate_settings_returns_no_issues_when_edge_voice_present(self):
        new_settings = _make_settings(api_key="sk-ant-test")

        issue = self.service.validate_settings(new_settings)

        self.assertIsNone(issue)

    def test_validate_settings_uses_the_provider_the_user_is_switching_to(self):
        new_settings = _make_settings(
            api_key="sk-ant-test", provider=_make_chatterbox_provider(profile="")
        )

        issue = self.service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.field, "profile")

    def test_reload_service_rebuilds_provider_from_settings_handler(self):
        new_settings = _make_settings(api_key="sk-ant-test")
        new_settings.tts.provider.voice = "en-US-GuyNeural"
        self.settings_handler.get_settings.return_value = new_settings

        self.service.reload_service()

        self.assertEqual(
            self.service.provider.provider_settings.voice, "en-US-GuyNeural"
        )

    async def test_get_tts_voices_returns_short_names_from_edge_tts_list_voices(self):
        available_voices = [
            {"ShortName": "en-US-AriaNeural", "Locale": "en-US"},
            {"ShortName": "en-GB-SoniaNeural", "Locale": "en-GB"},
        ]
        with patch(
            "edceleste.services.tts_service.edge_tts.list_voices",
            new=AsyncMock(return_value=available_voices),
        ):
            result = await self.service.get_tts_voices()

        self.assertEqual(result, ["en-US-AriaNeural", "en-GB-SoniaNeural"])

    async def test_get_tts_voices_returns_empty_list_when_no_voices_available(self):
        with patch(
            "edceleste.services.tts_service.edge_tts.list_voices",
            new=AsyncMock(return_value=[]),
        ):
            result = await self.service.get_tts_voices()

        self.assertEqual(result, [])

    async def test_get_tts_voices_propagates_error_when_edge_tts_list_voices_fails(
        self,
    ):
        with patch(
            "edceleste.services.tts_service.edge_tts.list_voices",
            new=AsyncMock(side_effect=RuntimeError("network down")),
        ):
            with self.assertRaises(RuntimeError):
                await self.service.get_tts_voices()

    async def test_clone_voice_delegates_to_the_chatterbox_provider(self):
        self.service.provider = Mock(spec=ChatterboxTTSProvider)

        await self.service.clone_voice("C:/audio/celeste.wav", "celeste")

        self.service.provider.clone_voice.assert_called_once_with(
            "C:/audio/celeste.wav", "celeste"
        )

    async def test_clone_voice_is_rejected_when_provider_cannot_clone_voices(self):
        self.service.provider = Mock(spec=EdgeTTSProvider)

        with self.assertRaises(VoiceCloningException):
            await self.service.clone_voice("C:/audio/celeste.wav", "celeste")

    async def test_clone_voice_propagates_error_raised_by_the_provider(self):
        self.service.provider = Mock(spec=ChatterboxTTSProvider)
        self.service.provider.clone_voice.side_effect = FileNotFoundError("no file")

        with self.assertRaises(FileNotFoundError):
            await self.service.clone_voice("C:/audio/celeste.wav", "celeste")


if __name__ == "__main__":
    unittest.main()
