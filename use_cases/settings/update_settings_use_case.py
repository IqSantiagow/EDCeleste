from protocols.event_reactions_protocol import EventReactionsProtocol
from protocols.keybinds_protocol import KeybindsProtocol
from protocols.journal_watcher_protocol import JournalWatcherProtocol
from protocols.llm_protocol import LLMProtocol
from protocols.settings_protocol import SettingsProtocol
from protocols.stt_protocol import SttProtocol
from protocols.tts_protocol import TTSProtocol
from services.models.settings_model import SettingsModel
from use_cases.settings.exceptions.settings_validation_exception import (
    SettingsValidationException,
)


class UpdateSettingsUseCase:
    def __init__(
        self,
        tts_service: TTSProtocol,
        stt_service: SttProtocol,
        journal_watcher_service: JournalWatcherProtocol,
        keybinds_service: KeybindsProtocol,
        llm_service: LLMProtocol,
        event_reactions_service: EventReactionsProtocol,
        settings_service: SettingsProtocol,
    ) -> None:
        self.tts_service = tts_service
        self.stt_service = stt_service
        self.journal_watcher_service = journal_watcher_service
        self.keybinds_service = keybinds_service
        self.llm_service = llm_service
        self.event_reactions_service = event_reactions_service
        self.settings_service = settings_service

    def __call__(self, new_settings: SettingsModel):
        tts_issues = self.tts_service.validate_settings(new_settings)
        stt_issues = self.stt_service.validate_settings(new_settings)
        journal_issues = self.journal_watcher_service.validate_settings(new_settings)
        keybinds_issues = self.keybinds_service.validate_settings(new_settings)
        llm_issues = self.llm_service.validate_settings(new_settings)
        event_reactions_issues = self.event_reactions_service.validate_settings(
            new_settings
        )

        issues = []

        if tts_issues:
            issues.append(tts_issues)
        if stt_issues:
            issues.append(stt_issues)
        if journal_issues:
            issues.append(journal_issues)
        if keybinds_issues:
            issues.append(keybinds_issues)
        if llm_issues:
            issues.append(llm_issues)
        if event_reactions_issues:
            issues.append(event_reactions_issues)

        if issues:
            raise SettingsValidationException(issues)

        self.settings_service.update_settings(new_settings)

        self.tts_service.reload_service()
        self.stt_service.reload_service()
        self.journal_watcher_service.reload_service()
        self.keybinds_service.reload_service()
        self.llm_service.reload_service()
        self.event_reactions_service.reload_service()
