import os
import unittest
from unittest.mock import patch

from edceleste.config.config import AppConfig

BASE_ENV = {
    "LOGGING__LEVEL": "INFO",
}


class TestAppConfig(unittest.TestCase):
    def test_app_config_builds_from_env_vars(self):
        with patch.dict(os.environ, BASE_ENV, clear=True):
            config = AppConfig(_env_file=None)  # type: ignore[call-arg]

        self.assertEqual(config.logging.level, "INFO")

    def test_app_config_requires_logging_level(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(Exception):
                AppConfig(_env_file=None)  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
