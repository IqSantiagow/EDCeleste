import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

import numpy as np

from edceleste.services.exceptions.stt_exception import SttException
from edceleste.services.llm_service import SYSTEM_PROMPT
from edceleste.services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from edceleste.services.settings_service import SettingsService
from edceleste.services.stt_service import SttService

MODEL = "tiny.en"


def _make_settings(
    model: str, enabled: bool = True, input_device: int | None = None
) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(volume=1.0),
        llm=LLMModel(
            api_key="sk-ant-test", system_prompt=SYSTEM_PROMPT, user_prompt=""
        ),
        stt=SttModel(model=model, enabled=enabled, input_device=input_device),
    )


class SttServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # sounddevice needs a working PortAudio install; fake the module so
        # tests run on systems (like headless CI) that don't have it.
        self.fake_sounddevice_module = MagicMock()
        sounddevice_patcher = patch.dict(
            sys.modules, {"sounddevice": self.fake_sounddevice_module}
        )
        sounddevice_patcher.start()
        self.addCleanup(sounddevice_patcher.stop)

        load_model_patcher = patch("edceleste.services.stt_service.whisper.load_model")

        self.mock_load_model = load_model_patcher.start()

        self.addCleanup(load_model_patcher.stop)

        self.mock_whisper_model = self.mock_load_model.return_value
        self.mock_whisper_model.transcribe.return_value = {
            "text": "Turn on the engines"
        }

        self.mock_input_stream_cls = self.fake_sounddevice_module.InputStream
        self.mock_stream = MagicMock()
        self.mock_input_stream_cls.return_value = self.mock_stream

        self.settings_handler = Mock(spec=SettingsService)
        self.settings_handler.get_settings.return_value = _make_settings(model=MODEL)

        self.service = SttService(settings_handler=self.settings_handler)

    # --- start_recording ---

    def test_start_recording_raises_when_disabled(self):
        self.service.enabled = False

        with self.assertRaises(SttException):
            self.service.start_recording()

        self.mock_input_stream_cls.assert_not_called()

    def test_start_recording_raises_when_already_recording(self):
        self.service.start_recording()

        with self.assertRaises(SttException):
            self.service.start_recording()

    def test_start_recording_opens_and_starts_stream(self):
        self.service.start_recording()

        self.mock_input_stream_cls.assert_called_once()
        self.mock_stream.start.assert_called_once()

    def test_start_recording_resets_recorded_frames(self):
        self.service._recorded_frames = [np.array([0.1, 0.2])]

        self.service.start_recording()

        self.assertEqual(self.service._recorded_frames, [])

    # --- stop_recording ---

    def test_stop_recording_raises_when_no_recording_in_progress(self):
        with self.assertRaises(SttException):
            self.service.stop_recording()

    def test_stop_recording_stops_and_closes_stream(self):
        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]

        self.service.stop_recording()

        self.mock_stream.stop.assert_called_once()
        self.mock_stream.close.assert_called_once()

    def test_stop_recording_clears_stream_reference(self):
        self.service.start_recording()

        self.service.stop_recording()

        self.assertIsNone(self.service._recording_stream)

    def test_stop_recording_returns_none_when_no_frames_captured(self):
        self.service.start_recording()
        # _recorded_frames already empty after start_recording

        result = self.service.stop_recording()

        self.assertIsNone(result)
        self.mock_whisper_model.transcribe.assert_not_called()

    def test_stop_recording_raises_when_model_not_set(self):
        self.service.model = None
        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]

        with self.assertRaises(SttException):
            self.service.stop_recording()

        self.mock_whisper_model.transcribe.assert_not_called()

    def test_stop_recording_returns_transcribed_text(self):
        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]

        result = self.service.stop_recording()

        self.assertEqual(result, "Turn on the engines")
        self.mock_whisper_model.transcribe.assert_called_once()

    def test_stop_recording_returns_none_when_transcription_empty(self):
        self.mock_whisper_model.transcribe.return_value = {"text": ""}
        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]

        result = self.service.stop_recording()

        self.assertIsNone(result)

    def test_stop_recording_loads_whisper_model_lazily_on_first_call(self):
        self.mock_load_model.assert_not_called()  # not loaded during __init__

        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]
        self.service.stop_recording()

        self.mock_load_model.assert_called_once_with(MODEL)

    def test_stop_recording_caches_whisper_model_across_calls(self):
        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]
        self.service.stop_recording()
        self.mock_load_model.reset_mock()

        self.mock_input_stream_cls.return_value = MagicMock()
        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]
        self.service.stop_recording()

        self.mock_load_model.assert_not_called()

    # --- validate_settings ---

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

    # --- reload_service ---

    def test_reload_service_updates_model_from_settings_handler(self):
        new_settings = _make_settings(model="base.en")
        self.settings_handler.get_settings.return_value = new_settings

        self.service.reload_service()

        self.assertEqual(self.service.model, "base.en")

    def test_reload_service_updates_enabled_from_settings_handler(self):
        new_settings = _make_settings(model=MODEL, enabled=False)
        self.settings_handler.get_settings.return_value = new_settings

        self.service.reload_service()

        self.assertFalse(self.service.enabled)

    def test_reload_service_invalidates_cache_when_model_changes(self):
        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]
        self.service.stop_recording()
        self.assertIsNotNone(self.service.whisper_model)

        self.settings_handler.get_settings.return_value = _make_settings(
            model="base.en"
        )
        self.service.reload_service()

        self.assertIsNone(self.service.whisper_model)

    def test_reload_service_invalidates_cache_when_enabled_changes(self):
        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]
        self.service.stop_recording()
        self.assertIsNotNone(self.service.whisper_model)

        self.settings_handler.get_settings.return_value = _make_settings(
            model=MODEL, enabled=False
        )
        self.service.reload_service()

        self.assertIsNone(self.service.whisper_model)

    def test_reload_service_keeps_cache_when_settings_unchanged(self):
        self.service.start_recording()
        self.service._recorded_frames = [np.array([0.1, 0.2])]
        self.service.stop_recording()
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

    # --- is_stt_enabled ---

    def test_is_stt_enabled_reflects_state(self):
        self.service.enabled = True
        self.assertTrue(self.service.is_stt_enabled())

        self.service.enabled = False
        self.assertFalse(self.service.is_stt_enabled())

    # --- get_stt_models ---

    def test_get_stt_models_returns_available_whisper_models(self):
        with patch(
            "edceleste.services.stt_service.whisper.available_models",
            return_value=["tiny.en", "base.en"],
        ):
            result = self.service.get_stt_models()

        self.assertEqual(result, ["tiny.en", "base.en"])


if __name__ == "__main__":
    unittest.main()
