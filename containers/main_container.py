from dependency_injector import containers, providers

from config.config import AppConfig
from services.event_bus import EventBus
from services.game_state_service import GameStateService
from services.journal_watcher_service import JournalWatcherService
from services.keybinds_service import KeybindService
from services.llm_service import LLMService
from services.stubs.journal_watcher_service_stub import JournalWatcherServiceStub
from services.tts_service import TTSService
from ui.screens.settings.settings_repository import SettingsRepository
from ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository
from use_cases.dashboard.journal_get_healtcheck_usecase import (
    JournalGetHealthCheckUseCase,
)
from use_cases.dashboard.llm_get_healthcheck_usecase import LlmGetHealthCheckUseCase
from use_cases.dashboard.llm_send_message_use_case import LLMSendMessageUseCase
from use_cases.dashboard.stream_dashboard_stats_usecase import (
    StreamDashboardStatsUseCase,
)
from use_cases.dashboard.stream_journal_events_usecase import StreamJournalEventsUseCase
from use_cases.dashboard.stream_llm_responses_use_case import StreamLLMResponsesUseCase
from use_cases.dashboard.stream_llm_state_use_case import StreamLLMStateUseCase
from use_cases.settings.settings_get_keybinds_use_case import SettingsGetKeybindsUseCase
from use_cases.settings.settings_load_keybinds_use_case import (
    SettingsLoadKeybindsUseCase,
)


class Container(containers.DeclarativeContainer):
    # -----CONFIG-----
    config = providers.Configuration(pydantic_settings=[AppConfig()])  # type: ignore

    # -----SERVICES-----

    event_bus = providers.Singleton(EventBus)

    llm_service = providers.Singleton(
        LLMService, api_key=config.llm.anthropic_api_key, event_bus=event_bus
    )

    journal_watcher_service = providers.Singleton(
        JournalWatcherService, journal_path=config.ed.main_path, event_bus=event_bus
    )

    journal_watcher_service_stub = providers.Singleton(
        JournalWatcherServiceStub, event_bus=event_bus
    )

    game_state_service = providers.Singleton(GameStateService, event_bus=event_bus)

    keybinds_service = providers.Singleton(
        KeybindService, keybinds_path=config.ed.keybinds_path, event_bus=event_bus
    )

    tts_service = providers.Singleton(
        TTSService, voice=config.tts.voice, event_bus=event_bus
    )

    # -----USE CASES-----
    stream_dashboard_stats_use_case = providers.Factory(
        StreamDashboardStatsUseCase, game_state_reader=game_state_service
    )

    journal_get_healthcheck_use_case = providers.Factory(
        JournalGetHealthCheckUseCase, journal_watcher_reader=journal_watcher_service
    )

    llm_get_healthcheck_use_case = providers.Factory(
        LlmGetHealthCheckUseCase, llm_protocol=llm_service
    )

    stream_journal_events_use_case = providers.Factory(
        StreamJournalEventsUseCase, game_state_reader=game_state_service
    )

    llm_send_message_use_case = providers.Factory(
        LLMSendMessageUseCase,
        llm_protocol=llm_service,
        game_state_reader=game_state_service,
    )

    stream_llm_responses_use_case = providers.Factory(
        StreamLLMResponsesUseCase, llm_protocol=llm_service
    )

    stream_llm_state_use_case = providers.Factory(
        StreamLLMStateUseCase, llm_protocol=llm_service
    )

    settings_load_keybinds_use_case = providers.Factory(
        SettingsLoadKeybindsUseCase, keybinds_protocol=keybinds_service
    )

    settings_get_keybinds_use_case = providers.Factory(
        SettingsGetKeybindsUseCase, keybinds_protocol=keybinds_service
    )

    # -----REPOSITORIES-----
    ed_dashboard_repository = providers.Singleton(
        EdDashboardRepository,
        stream_dashboard_stats_usecase=stream_dashboard_stats_use_case,
        stream_journal_events_usecase=stream_journal_events_use_case,
        journal_get_healthcheck_usecase=journal_get_healthcheck_use_case,
        llm_get_healthcheck_usecase=llm_get_healthcheck_use_case,
        llm_send_message_usecase=llm_send_message_use_case,
        stream_llm_responses_usecase=stream_llm_responses_use_case,
        stream_llm_state_usecase=stream_llm_state_use_case,
    )

    settings_repository = providers.Singleton(
        SettingsRepository,
        settings_load_keybinds_use_case=settings_load_keybinds_use_case,
        settings_get_keybinds_use_case=settings_get_keybinds_use_case,
    )
