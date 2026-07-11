import os
import unittest
from unittest.mock import patch

from config.config import AppConfig, LangSmithConfig, TTSConfig

BASE_ENV = {
    "ED__MAIN_PATH": "C:/ed",
    "ED__KEYBINDS_PATH": "C:/keybinds",
    "ED__LOGGING__LEVEL": "INFO",
    "LLM__ANTHROPIC_API_KEY": "sk-ant-test",
}


class TestAppConfig(unittest.TestCase):
    def test_app_config_builds_from_env_vars_including_langsmith_settings(self):
        env = {
            **BASE_ENV,
            "LANGSMITH__TRACING": "true",
            "LANGSMITH__API_KEY": "lsv2-test",
            "LANGSMITH__PROJECT": "TestProject",
            "LANGSMITH__ENDPOINT": "https://example.com",
        }

        with patch.dict(os.environ, env, clear=True):
            config = AppConfig(_env_file=None)  # type: ignore[call-arg]

        self.assertEqual(config.ed.main_path, "C:/ed")
        self.assertEqual(config.llm.anthropic_api_key, "sk-ant-test")
        self.assertTrue(config.langsmith.tracing)
        self.assertEqual(config.langsmith.api_key, "lsv2-test")
        self.assertEqual(config.langsmith.project, "TestProject")
        self.assertEqual(config.langsmith.endpoint, "https://example.com")

    def test_app_config_uses_default_langsmith_config_when_env_vars_absent(self):
        with patch.dict(os.environ, BASE_ENV, clear=True):
            config = AppConfig(_env_file=None)  # type: ignore[call-arg]

        self.assertEqual(config.langsmith, LangSmithConfig())

    def test_app_config_falls_back_to_langsmith_defaults_when_one_var_is_set(self):
        env = {**BASE_ENV, "LANGSMITH__TRACING": "false"}

        with patch.dict(os.environ, env, clear=True):
            config = AppConfig(_env_file=None)  # type: ignore[call-arg]

        self.assertFalse(config.langsmith.tracing)
        self.assertEqual(config.langsmith.api_key, "")
        self.assertEqual(config.langsmith.project, "EDCeleste")
        self.assertEqual(config.langsmith.endpoint, "https://api.smith.langchain.com")

    def test_app_config_uses_default_tts_config_when_env_vars_absent(self):
        with patch.dict(os.environ, BASE_ENV, clear=True):
            config = AppConfig(_env_file=None)  # type: ignore[call-arg]

        self.assertEqual(config.tts, TTSConfig())
        self.assertEqual(config.tts.voice, "en-GB-SoniaNeural")

    def test_app_config_builds_tts_config_from_env_var(self):
        env = {**BASE_ENV, "TTS__VOICE": "en-US-AriaNeural"}

        with patch.dict(os.environ, env, clear=True):
            config = AppConfig(_env_file=None)  # type: ignore[call-arg]

        self.assertEqual(config.tts.voice, "en-US-AriaNeural")


if __name__ == "__main__":
    unittest.main()
