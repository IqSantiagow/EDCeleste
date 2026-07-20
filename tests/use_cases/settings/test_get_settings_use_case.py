import unittest
from unittest.mock import Mock

from services.models.settings_model import LLMModel, PathModel, SettingsModel, TTSModel
from use_cases.settings.get_settings_use_case import GetSettingsUseCase


def _make_settings() -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="sp", user_prompt=""),
    )


class TestGetSettingsUseCase(unittest.TestCase):
    def test_should_return_settings_from_protocol(self):
        settings = _make_settings()
        protocol = Mock()
        protocol.get_settings.return_value = settings
        use_case = GetSettingsUseCase(protocol)  # type: ignore

        result = use_case()

        self.assertEqual(result, settings)
        protocol.get_settings.assert_called_once()


if __name__ == "__main__":
    unittest.main()
