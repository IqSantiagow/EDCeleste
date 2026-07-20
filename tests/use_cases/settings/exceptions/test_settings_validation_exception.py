import unittest

from services.models.settings_model import SettingsIssueModel
from use_cases.settings.exceptions.settings_validation_exception import (
    SettingsValidationException,
)


class TestSettingsValidationException(unittest.TestCase):
    def test_stores_issues_and_builds_message(self):
        issues = [
            SettingsIssueModel(
                section="tts", field="voice", message="Voice is not set."
            )
        ]

        exception = SettingsValidationException(issues)

        self.assertEqual(exception.issues, issues)
        self.assertIn("Voice is not set.", str(exception))


if __name__ == "__main__":
    unittest.main()
