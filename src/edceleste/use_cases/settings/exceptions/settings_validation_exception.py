from edceleste.services.models.settings_model import SettingsIssueModel


class SettingsValidationException(Exception):
    def __init__(self, issues: list[SettingsIssueModel]):
        """Carries every issue found, not only the first one, so the settings
        screen can mark all wrong fields at once."""
        self.issues = issues
        super().__init__(f"Settings validation failed with issues: {issues}")
