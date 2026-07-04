import os
import unittest
from unittest.mock import patch

from config.config import LangSmithConfig
from config.tracing import configure_langsmith


class TestConfigureLangsmith(unittest.TestCase):
    def test_should_not_set_env_when_tracing_disabled(self):
        config = LangSmithConfig(tracing=False, api_key="secret", project="Proj")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LANGSMITH_TRACING", None)
            os.environ.pop("LANGSMITH_API_KEY", None)

            configure_langsmith(config)

            self.assertNotIn("LANGSMITH_TRACING", os.environ)
            self.assertNotIn("LANGSMITH_API_KEY", os.environ)

    def test_should_set_env_vars_when_tracing_enabled(self):
        config = LangSmithConfig(
            tracing=True,
            api_key="secret-key",
            project="EDCeleste",
            endpoint="https://example.com",
        )

        with patch.dict(os.environ, {}, clear=False):
            configure_langsmith(config)

            self.assertEqual(os.environ["LANGSMITH_TRACING"], "True")
            self.assertEqual(os.environ["LANGSMITH_API_KEY"], "secret-key")
            self.assertEqual(os.environ["LANGSMITH_PROJECT"], "EDCeleste")
            self.assertEqual(os.environ["LANGSMITH_ENDPOINT"], "https://example.com")


if __name__ == "__main__":
    unittest.main()
