import unittest
from unittest.mock import mock_open, patch

from services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from services.settings_service import SettingsService


def _make_settings(system_prompt: str = "sp", journal_path: str = "C:/j"):
    return SettingsModel(
        paths=PathModel(journal_path=journal_path, keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(system_prompt=system_prompt, user_prompt="up"),
        stt=SttModel(model="tiny.en"),
    )


class SettingsServiceTest(unittest.TestCase):
    def test_get_settings_raises_before_load(self):
        service = SettingsService()

        with self.assertRaises(RuntimeError):
            service.get_settings()

    @patch("services.settings_service.glob", return_value=["config.yaml"])
    def test_load_settings_populates_settings_from_yaml(self, _mock_glob):
        service = SettingsService()
        yaml_content = """
paths:
  journal_path: C:/j
  keybindings_path: C:/k
tts:
  voice: en-GB-SoniaNeural
  volume: 1.0
llm:
  system_prompt: sp
  user_prompt: up
stt:
  model: tiny.en
"""
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            service.load_settings()

        self.assertEqual(service.get_settings().llm.system_prompt, "sp")

    @patch("services.settings_service.os.path.exists", return_value=True)
    @patch("services.settings_service.shutil.copyfile")
    @patch("services.settings_service.glob", return_value=[])
    def test_load_settings_creates_config_from_example_and_raises_when_missing(
        self, _mock_glob, mock_copy, _mock_exists
    ):
        service = SettingsService()

        with self.assertRaises(FileNotFoundError):
            service.load_settings()

        mock_copy.assert_called_once_with("config-example.yaml", "config.yaml")

    @patch("services.settings_service.os.path.exists", return_value=False)
    @patch("services.settings_service.shutil.copyfile")
    @patch("services.settings_service.glob", return_value=[])
    def test_load_settings_raises_runtime_error_when_copy_from_example_fails(
        self, _mock_glob, mock_copy, _mock_exists
    ):
        service = SettingsService()

        with self.assertRaises(RuntimeError):
            service.load_settings()

        mock_copy.assert_called_once_with("config-example.yaml", "config.yaml")

    @patch("services.settings_service.glob", return_value=["config.yaml"])
    def test_load_settings_raises_runtime_error_on_invalid_yaml_schema(
        self, _mock_glob
    ):
        service = SettingsService()
        yaml_content = """
paths:
  journal_path: C:/j
  keybindings_path: C:/k
tts:
  voice: en-GB-SoniaNeural
  volume: 1.0
"""

        with patch("builtins.open", mock_open(read_data=yaml_content)):
            with self.assertRaises(RuntimeError):
                service.load_settings()

    @patch("services.settings_service.glob", return_value=["config.yaml"])
    def test_update_settings_writes_yaml_when_one_section_changed(self, _mock_glob):
        service = SettingsService()
        service.settings = _make_settings(system_prompt="old")
        new_settings = _make_settings(system_prompt="new")

        with patch("builtins.open", mock_open()):
            with patch("services.settings_service.yaml.safe_dump") as mock_dump:
                service.update_settings(new_settings)

        mock_dump.assert_called_once()
        self.assertEqual(service.get_settings().llm.system_prompt, "new")

    @patch("services.settings_service.glob", side_effect=[[], ["config.yaml"]])
    @patch("services.settings_service.shutil.copyfile")
    def test_update_settings_creates_config_yaml_from_example_when_missing(
        self, mock_copy, mock_glob
    ):
        service = SettingsService()
        service.settings = _make_settings(system_prompt="old")
        new_settings = _make_settings(system_prompt="new")

        with patch("builtins.open", mock_open()):
            service.update_settings(new_settings)

        mock_copy.assert_called_once_with("config-example.yaml", "config.yaml")
        self.assertEqual(mock_glob.call_count, 2)


if __name__ == "__main__":
    unittest.main()
