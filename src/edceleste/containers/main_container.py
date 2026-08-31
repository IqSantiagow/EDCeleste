from dependency_injector import containers, providers

from edceleste.adapters.tools.perform_game_action import PerformGameAction
from edceleste.config.config import AppConfig
from edceleste.services.event_bus import EventBus
from edceleste.services.event_reactions_service import EventReactionsService
from edceleste.services.game_state_service import GameStateService
from edceleste.services.journal_watcher_service import JournalWatcherService
from edceleste.services.keybinds_service import KeybindService
from edceleste.services.llm_service import LLMService
from edceleste.services.stt_service import SttService
from edceleste.services.stubs.journal_watcher_service_stub import (
    JournalWatcherServiceStub,
)
from edceleste.services.tts_service import TTSService
from edceleste.services.settings_service import SettingsService
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository
from edceleste.use_cases.dashboard.llm_send_message_use_case import (
    LLMSendMessageUseCase,
)
from edceleste.use_cases.dashboard.stream_dashboard_stats_usecase import (
    StreamDashboardStatsUseCase,
)
from edceleste.use_cases.dashboard.stream_journal_events_usecase import (
    StreamJournalEventsUseCase,
)
from edceleste.use_cases.dashboard.stream_llm_responses_use_case import (
    StreamLLMResponsesUseCase,
)
from edceleste.use_cases.settings.clone_voice_use_case import CloneVoiceUseCase
from edceleste.use_cases.settings.get_settings_use_case import GetSettingsUseCase
from edceleste.use_cases.settings.get_stt_models_use_case import GetSttModelsUseCase
from edceleste.use_cases.settings.get_stt_input_devices_use_case import (
    GetSttInputDevicesUseCase,
)
from edceleste.use_cases.settings.get_tts_voices_use_case import GetTTSVoicesUseCase
from edceleste.use_cases.settings.settings_get_keybinds_use_case import (
    SettingsGetKeybindsUseCase,
)
from edceleste.use_cases.settings.settings_load_keybinds_use_case import (
    SettingsLoadKeybindsUseCase,
)
from edceleste.use_cases.dashboard.stt_start_recording_use_case import (
    SttStartRecordingUseCase,
)
from edceleste.use_cases.dashboard.stt_stop_recording_use_case import (
    SttStopRecordingUseCase,
)
from edceleste.use_cases.dashboard.get_stt_enabled_use_case import GetSttEnabledUseCase
from edceleste.use_cases.settings.update_settings_use_case import UpdateSettingsUseCase


def _build_loaded_settings_service() -> SettingsService:
    # TODO: Add initial setting to further load it during the app settings screen
    settings_service = SettingsService()
    settings_service.load_settings()
    return settings_service


class Container(containers.DeclarativeContainer):
    # -----CONFIG-----
    config = providers.Configuration(pydantic_settings=[AppConfig()])  # type: ignore

    # -----TOOLS-----

    settings_service = providers.Singleton(_build_loaded_settings_service)

    event_bus = providers.Singleton(EventBus)

    journal_watcher_service = providers.Singleton(
        JournalWatcherService,
        journal_path=settings_service.provided.get_settings.call().paths.journal_path,
        event_bus=event_bus,
        settings_handler=settings_service,
    )

    game_state_service = providers.Singleton(GameStateService, event_bus=event_bus)

    keybinds_service = providers.Singleton(
        KeybindService,
        keybinds_path=(
            settings_service.provided.get_settings.call().paths.keybindings_path
        ),
        event_bus=event_bus,
        settings_handler=settings_service,
    )

    perform_game_action = providers.Factory(
        PerformGameAction,
        keybind_service=keybinds_service,
        settings_service=settings_service,
    )

    # ----- MCP------
    mcps = providers.List(
        perform_game_action,
    )

    llm_service = providers.Singleton(
        LLMService, event_bus=event_bus, settings_service=settings_service, tools=mcps
    )

    journal_watcher_service_stub = providers.Singleton(
        JournalWatcherServiceStub,
        event_bus=event_bus,
        settings_handler=settings_service,
    )

    tts_service = providers.Singleton(
        TTSService,
        event_bus=event_bus,
        settings_handler=settings_service,
    )

    stt_service = providers.Singleton(
        SttService,
        settings_handler=settings_service,
    )

    event_reactions_service = providers.Singleton(
        EventReactionsService,
        event_bus=event_bus,
        settings_service=settings_service,
    )

    # -----USE CASES-----
    stream_dashboard_stats_use_case = providers.Factory(
        StreamDashboardStatsUseCase, game_state_reader=game_state_service
    )

    stream_journal_events_use_case = providers.Factory(
        StreamJournalEventsUseCase, game_state_reader=game_state_service
    )

    llm_send_message_use_case = providers.Factory(
        LLMSendMessageUseCase,
        llm_protocol=llm_service,
    )

    stream_llm_responses_use_case = providers.Factory(
        StreamLLMResponsesUseCase, llm_protocol=llm_service
    )

    stt_start_recording_use_case = providers.Factory(
        SttStartRecordingUseCase, stt_protocol=stt_service
    )

    stt_stop_recording_use_case = providers.Factory(
        SttStopRecordingUseCase, stt_protocol=stt_service
    )

    get_stt_enabled_use_case = providers.Factory(
        GetSttEnabledUseCase, stt_protocol=stt_service
    )

    settings_load_keybinds_use_case = providers.Factory(
        SettingsLoadKeybindsUseCase, keybinds_protocol=keybinds_service
    )

    settings_get_keybinds_use_case = providers.Factory(
        SettingsGetKeybindsUseCase, keybinds_protocol=keybinds_service
    )

    update_settings_use_case = providers.Factory(
        UpdateSettingsUseCase,
        tts_service=tts_service,
        stt_service=stt_service,
        journal_watcher_service=journal_watcher_service,
        keybinds_service=keybinds_service,
        llm_service=llm_service,
        event_reactions_service=event_reactions_service,
        settings_service=settings_service,
    )

    get_settings_use_case = providers.Factory(
        GetSettingsUseCase, settings_protocol=settings_service
    )

    get_tts_voices_use_case = providers.Factory(
        GetTTSVoicesUseCase, tts_protocol=tts_service
    )

    clone_voice_use_case = providers.Factory(
        CloneVoiceUseCase, voice_cloning_protocol=tts_service
    )

    get_stt_models_use_case = providers.Factory(
        GetSttModelsUseCase, stt_protocol=stt_service
    )

    get_stt_input_devices_use_case = providers.Factory(
        GetSttInputDevicesUseCase, stt_protocol=stt_service
    )

    # -----REPOSITORIES-----
    ed_dashboard_repository = providers.Singleton(
        EdDashboardRepository,
        stream_dashboard_stats_usecase=stream_dashboard_stats_use_case,
        stream_journal_events_usecase=stream_journal_events_use_case,
        llm_send_message_usecase=llm_send_message_use_case,
        stream_llm_responses_usecase=stream_llm_responses_use_case,
        stt_start_recording_usecase=stt_start_recording_use_case,
        stt_stop_recording_usecase=stt_stop_recording_use_case,
        get_stt_enabled_usecase=get_stt_enabled_use_case,
    )

    settings_repository = providers.Singleton(
        SettingsRepository,
        settings_load_keybinds_use_case=settings_load_keybinds_use_case,
        settings_get_keybinds_use_case=settings_get_keybinds_use_case,
        update_settings_use_case=update_settings_use_case,
        get_settings_use_case=get_settings_use_case,
        get_tts_voices_use_case=get_tts_voices_use_case,
        get_stt_models_use_case=get_stt_models_use_case,
        get_stt_input_devices_use_case=get_stt_input_devices_use_case,
        clone_voice_use_case=clone_voice_use_case,
    )
