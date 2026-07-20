from services.models.settings_model import SettingsIssueModel


class SettingsValidationException(Exception):
    def __init__(self, issues: list[SettingsIssueModel]):
        self.issues = issues
        super().__init__(f"Settings validation failed with issues: {issues}")
