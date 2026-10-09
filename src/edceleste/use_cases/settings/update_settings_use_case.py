from edceleste.protocols.event_reactions_protocol import EventReactionsProtocol
from edceleste.protocols.keybinds_protocol import KeybindsProtocol
from edceleste.protocols.game_watcher_protocol import GameWatcherProtocol
from edceleste.protocols.instinct_protocol import InstinctProtocol
from edceleste.protocols.llm_protocol import LLMProtocol
from edceleste.protocols.settings_protocol import SettingsProtocol
from edceleste.protocols.stt_protocol import SttProtocol
from edceleste.protocols.tts_protocol import TTSProtocol
from edceleste.services.models.settings_model import SettingsModel
from edceleste.use_cases.settings.exceptions.settings_validation_exception import (
    SettingsValidationException,
)


class UpdateSettingsUseCase:
    def __init__(
        self,
        tts_service: TTSProtocol,
        stt_service: SttProtocol,
        game_watcher_service: GameWatcherProtocol,
        keybinds_service: KeybindsProtocol,
        llm_service: LLMProtocol,
        instinct_service: InstinctProtocol,
        event_reactions_service: EventReactionsProtocol,
        settings_service: SettingsProtocol,
    ) -> None:
        self.tts_service = tts_service
        self.stt_service = stt_service
        self.game_watcher_service = game_watcher_service
        self.keybinds_service = keybinds_service
        self.llm_service = llm_service
        self.instinct_service = instinct_service
        self.event_reactions_service = event_reactions_service
        self.settings_service = settings_service

    async def __call__(self, new_settings: SettingsModel):
        """Save button of the settings screen.

        1. Asks every service to validate new_settings. All of them run, so
           the pilot sees every issue at once. The LLM check goes to the
           network.
        2. Any issue -> raises SettingsValidationException with all issues,
           nothing is saved and no service changes.
        3. No issue -> writes config.yaml, then reloads every service, one
           after another, so each reads the new settings.
        A reload that raises stops the rest: the settings are already saved,
        but the services after it still run on the old settings.
        """
        tts_issues = self.tts_service.validate_settings(new_settings)
        stt_issues = self.stt_service.validate_settings(new_settings)
        game_watcher_issues = self.game_watcher_service.validate_settings(new_settings)
        keybinds_issues = self.keybinds_service.validate_settings(new_settings)
        llm_issues = await self.llm_service.validate_settings(new_settings)
        instinct_issues = self.instinct_service.validate_settings(new_settings)
        event_reactions_issues = self.event_reactions_service.validate_settings(
            new_settings
        )

        all_issues = [
            tts_issues,
            stt_issues,
            game_watcher_issues,
            keybinds_issues,
            llm_issues,
            instinct_issues,
            event_reactions_issues,
        ]

        issues = [issue for issue in all_issues if issue]

        if issues:
            raise SettingsValidationException(issues)

        self.settings_service.save_settings(new_settings)

        self.tts_service.reload_service()
        self.stt_service.reload_service()
        self.game_watcher_service.reload_service()
        self.keybinds_service.reload_service()
        self.llm_service.reload_service()
        self.instinct_service.reload_service()
        self.event_reactions_service.reload_service()
