import unittest
from unittest.mock import Mock, patch

from services.llm_service import SYSTEM_PROMPT
from services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from services.settings_service import SettingsService

from services.stt_service import SttService

MODEL = "tiny.en"


def _make_settings(model: str) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(
            api_key="sk-ant-test", system_prompt=SYSTEM_PROMPT, user_prompt=""
        ),
        stt=SttModel(model=model),
    )


class SttServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        load_model_patcher = patch("services.stt_service.whisper.load_model")
        exists_patcher = patch("services.stt_service.os.path.exists")

        self.mock_load_model = load_model_patcher.start()
        self.mock_exists = exists_patcher.start()

        self.addCleanup(load_model_patcher.stop)
        self.addCleanup(exists_patcher.stop)

        self.mock_exists.return_value = True
        self.mock_whisper_model = self.mock_load_model.return_value
        self.mock_whisper_model.transcribe.return_value = {
            "text": "Turn on the engines"
        }

        self.settings_handler = Mock(spec=SettingsService)
        self.settings_handler.get_settings.return_value = _make_settings(model=MODEL)

        self.service = SttService(settings_handler=self.settings_handler)

    def test_handle_stt_request_returns_none_when_model_not_set(self):
        self.service.model = None

        result = self.service.handle_stt_request("turn_on_the_engines_sample.mp3")

        self.assertIsNone(result)
        self.mock_load_model.assert_not_called()

    def test_handle_stt_request_returns_none_when_audio_path_is_empty(self):
        result = self.service.handle_stt_request("")

        self.assertIsNone(result)
        self.mock_load_model.assert_not_called()

    def test_handle_stt_request_returns_none_when_audio_path_does_not_exist(self):
        self.mock_exists.return_value = False

        result = self.service.handle_stt_request("missing.mp3")

        self.assertIsNone(result)
        self.mock_load_model.assert_not_called()

    def test_handle_stt_request_returns_transcribed_text_when_audio_exists(self):
        result = self.service.handle_stt_request("turn_on_the_engines_sample.mp3")

        self.assertEqual(result, "Turn on the engines")
        self.mock_load_model.assert_called_once_with(MODEL)
        self.mock_whisper_model.transcribe.assert_called_once_with(
            "turn_on_the_engines_sample.mp3"
        )

    def test_handle_stt_request_returns_none_when_transcription_text_is_empty(self):
        self.mock_whisper_model.transcribe.return_value = {"text": ""}

        result = self.service.handle_stt_request("turn_on_the_engines_sample.mp3")

        self.assertIsNone(result)

    def test_validate_settings_reports_issue_when_model_missing(self):
        new_settings = _make_settings(model="")

        issue = self.service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "stt")
        self.assertEqual(issue.field, "model")

    def test_validate_settings_returns_no_issues_when_model_present(self):
        new_settings = _make_settings(model=MODEL)

        issue = self.service.validate_settings(new_settings)

        self.assertIsNone(issue)

    def test_reload_service_updates_model_from_settings_handler(self):
        new_settings = _make_settings(model="base.en")
        self.settings_handler.get_settings.return_value = new_settings

        self.service.reload_service()

        self.assertEqual(self.service.model, "base.en")

    async def test_get_stt_models_returns_available_whisper_models(self):
        with patch(
            "services.stt_service.whisper.available_models",
            return_value=["tiny.en", "base.en"],
        ):
            result = await self.service.get_stt_models()

        self.assertEqual(result, ["tiny.en", "base.en"])


if __name__ == "__main__":
    unittest.main()
