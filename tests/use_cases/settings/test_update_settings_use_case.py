import unittest
from unittest.mock import Mock

from services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsIssueModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from use_cases.settings.exceptions.settings_validation_exception import (
    SettingsValidationException,
)
from use_cases.settings.update_settings_use_case import UpdateSettingsUseCase


def _make_settings() -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="sp", user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


def _make_issue(section: str) -> SettingsIssueModel:
    return SettingsIssueModel(section=section, field="some_field", message="broken")


class TestUpdateSettingsUseCase(unittest.TestCase):
    def setUp(self):
        self.tts_service = Mock()
        self.stt_service = Mock()
        self.journal_watcher_service = Mock()
        self.keybinds_service = Mock()
        self.llm_service = Mock()
        self.event_reactions_service = Mock()
        self.settings_service = Mock()

        for service in (
            self.tts_service,
            self.stt_service,
            self.journal_watcher_service,
            self.keybinds_service,
            self.llm_service,
            self.event_reactions_service,
        ):
            service.validate_settings.return_value = None

        self.use_case = UpdateSettingsUseCase(
            tts_service=self.tts_service,
            stt_service=self.stt_service,
            journal_watcher_service=self.journal_watcher_service,
            keybinds_service=self.keybinds_service,
            llm_service=self.llm_service,
            event_reactions_service=self.event_reactions_service,
            settings_service=self.settings_service,
        )

    def _assert_no_service_reloaded(self):
        self.settings_service.update_settings.assert_not_called()
        self.tts_service.reload_service.assert_not_called()
        self.stt_service.reload_service.assert_not_called()
        self.journal_watcher_service.reload_service.assert_not_called()
        self.keybinds_service.reload_service.assert_not_called()
        self.llm_service.reload_service.assert_not_called()
        self.event_reactions_service.reload_service.assert_not_called()

    def test_should_persist_and_reload_all_services_when_no_validation_issues(
        self,
    ):
        new_settings = _make_settings()

        self.use_case(new_settings)

        self.settings_service.update_settings.assert_called_once_with(new_settings)
        self.tts_service.reload_service.assert_called_once_with()
        self.stt_service.reload_service.assert_called_once_with()
        self.journal_watcher_service.reload_service.assert_called_once_with()
        self.keybinds_service.reload_service.assert_called_once_with()
        self.llm_service.reload_service.assert_called_once_with()
        self.event_reactions_service.reload_service.assert_called_once_with()

    def test_should_raise_and_not_persist_when_tts_has_issues(self):
        self.tts_service.validate_settings.return_value = _make_issue("tts")

        with self.assertRaises(SettingsValidationException):
            self.use_case(_make_settings())

        self._assert_no_service_reloaded()

    def test_should_raise_and_not_persist_when_stt_has_issues(self):
        self.stt_service.validate_settings.return_value = _make_issue("stt")

        with self.assertRaises(SettingsValidationException):
            self.use_case(_make_settings())

        self._assert_no_service_reloaded()

    def test_should_raise_and_not_persist_when_journal_watcher_has_issues(self):
        self.journal_watcher_service.validate_settings.return_value = _make_issue(
            "journal_watcher"
        )

        with self.assertRaises(SettingsValidationException):
            self.use_case(_make_settings())

        self._assert_no_service_reloaded()

    def test_should_raise_and_not_persist_when_keybinds_has_issues(self):
        self.keybinds_service.validate_settings.return_value = _make_issue("keybinds")

        with self.assertRaises(SettingsValidationException):
            self.use_case(_make_settings())

        self._assert_no_service_reloaded()

    def test_should_raise_and_not_persist_when_llm_has_issues(self):
        self.llm_service.validate_settings.return_value = _make_issue("llm")

        with self.assertRaises(SettingsValidationException):
            self.use_case(_make_settings())

        self._assert_no_service_reloaded()

    def test_should_raise_and_not_persist_when_event_reactions_has_issues(self):
        self.event_reactions_service.validate_settings.return_value = _make_issue(
            "event_reaction"
        )

        with self.assertRaises(SettingsValidationException):
            self.use_case(_make_settings())

        self._assert_no_service_reloaded()

    def test_should_aggregate_issues_from_multiple_services_in_exception(self):
        tts_issue = _make_issue("tts")
        llm_issue = _make_issue("llm")
        self.tts_service.validate_settings.return_value = tts_issue
        self.llm_service.validate_settings.return_value = llm_issue

        with self.assertRaises(SettingsValidationException) as ctx:
            self.use_case(_make_settings())

        self.assertEqual(ctx.exception.issues, [tts_issue, llm_issue])


if __name__ == "__main__":
    unittest.main()
