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

from services.exceptions.stt_exception import SttException
from services.stt_service import SttService

MODEL = "tiny.en"


def _make_settings(model: str, enabled: bool = True) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(
            api_key="sk-ant-test", system_prompt=SYSTEM_PROMPT, user_prompt=""
        ),
        stt=SttModel(model=model, enabled=enabled),
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

    def test_handle_stt_request_raises_when_model_not_set(self):
        self.service.model = None

        with self.assertRaises(SttException):
            self.service.handle_stt_request("turn_on_the_engines_sample.mp3")

        self.mock_whisper_model.transcribe.assert_not_called()

    def test_handle_stt_request_raises_when_audio_path_is_empty(self):
        with self.assertRaises(SttException):
            self.service.handle_stt_request("")

        self.mock_whisper_model.transcribe.assert_not_called()

    def test_handle_stt_request_raises_when_audio_path_does_not_exist(self):
        self.mock_exists.return_value = False

        with self.assertRaises(SttException):
            self.service.handle_stt_request("missing.mp3")

        self.mock_whisper_model.transcribe.assert_not_called()

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

    def test_handle_stt_request_raises_when_disabled(self):
        self.service.enabled = False

        with self.assertRaises(SttException):
            self.service.handle_stt_request("turn_on_the_engines_sample.mp3")

        self.mock_whisper_model.transcribe.assert_not_called()

    def test_reload_service_updates_enabled_from_settings_handler(self):
        new_settings = _make_settings(model=MODEL, enabled=False)
        self.settings_handler.get_settings.return_value = new_settings

        self.service.reload_service()

        self.assertFalse(self.service.enabled)

    def test_is_stt_enabled_reflects_state(self):
        self.service.enabled = True
        self.assertTrue(self.service.is_stt_enabled())

        self.service.enabled = False
        self.assertFalse(self.service.is_stt_enabled())

    def test_handle_stt_request_loads_model_lazily_on_first_call(self):
        self.mock_load_model.assert_not_called()  # not loaded during __init__

        self.service.handle_stt_request("audio.mp3")

        self.mock_load_model.assert_called_once_with(MODEL)

    def test_handle_stt_request_caches_model_across_calls(self):
        self.service.handle_stt_request("audio.mp3")
        self.mock_load_model.reset_mock()

        self.service.handle_stt_request("audio.mp3")

        self.mock_load_model.assert_not_called()

    def test_reload_service_invalidates_cache_when_model_changes(self):
        self.service.handle_stt_request("audio.mp3")  # warms up cache
        self.assertIsNotNone(self.service.whisper_model)

        self.settings_handler.get_settings.return_value = _make_settings(
            model="base.en"
        )
        self.service.reload_service()

        self.assertIsNone(self.service.whisper_model)

    def test_reload_service_invalidates_cache_when_enabled_changes(self):
        self.service.handle_stt_request("audio.mp3")  # warms up cache
        self.assertIsNotNone(self.service.whisper_model)

        self.settings_handler.get_settings.return_value = _make_settings(
            model=MODEL, enabled=False
        )
        self.service.reload_service()

        self.assertIsNone(self.service.whisper_model)

    def test_reload_service_keeps_cache_when_settings_unchanged(self):
        self.service.handle_stt_request("audio.mp3")  # warms up cache
        cached = self.service.whisper_model

        self.service.reload_service()  # same settings

        self.assertIs(self.service.whisper_model, cached)

    def test_reload_service_does_not_load_model_eagerly(self):
        self.settings_handler.get_settings.return_value = _make_settings(
            model="base.en"
        )
        self.mock_load_model.reset_mock()

        self.service.reload_service()

        self.mock_load_model.assert_not_called()
        self.assertIsNone(self.service.whisper_model)

    def test_reload_service_sets_whisper_model_none_when_model_absent(self):
        self.settings_handler.get_settings.return_value = _make_settings(model="")
        self.mock_load_model.reset_mock()

        self.service.reload_service()

        self.mock_load_model.assert_not_called()
        self.assertIsNone(self.service.whisper_model)

    def test_get_stt_models_returns_available_whisper_models(self):
        with patch(
            "services.stt_service.whisper.available_models",
            return_value=["tiny.en", "base.en"],
        ):
            result = self.service.get_stt_models()

        self.assertEqual(result, ["tiny.en", "base.en"])


if __name__ == "__main__":
    unittest.main()
