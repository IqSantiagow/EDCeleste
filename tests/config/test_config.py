import os
import unittest
from unittest.mock import patch

from edceleste.config.config import AppConfig, LangSmithConfig

BASE_ENV = {
    "LOGGING__LEVEL": "INFO",
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

        self.assertEqual(config.logging.level, "INFO")
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

    def test_app_config_requires_logging_level(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(Exception):
                AppConfig(_env_file=None)  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
