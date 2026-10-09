from dependency_injector import containers, providers

from edceleste.adapters.tools.perform_game_action import PerformGameAction
from edceleste.services.event_bus import EventBus
from edceleste.services.event_reactions_service import EventReactionsService
from edceleste.services.game_state_service import GameStateService
from edceleste.services.game_watcher_service import GameWatcherService
from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
)
from edceleste.services.game_window import GameWindow
from edceleste.services.instinct_service import InstinctService
from edceleste.services.keybinds_service import KeybindService
from edceleste.services.llm_service import LLMService
from edceleste.services.stt_service import SttService
from edceleste.services.tts_service import TTSService
from edceleste.services.settings_service import SettingsService
from edceleste.services.voice_lab_service import VoiceLabService
from edceleste.ui.screens.app.app_header_repository import AppHeaderRepository
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.system_check.system_check_repository import (
    SystemCheckRepository,
)
from edceleste.ui.screens.dashboard.ed_dashboard_repository import EdDashboardRepository
from edceleste.use_cases.dashboard.llm_send_message_use_case import (
    LLMSendMessageUseCase,
)
from edceleste.use_cases.app.stream_app_header_stats_usecase import (
    StreamAppHeaderStatsUseCase,
)
from edceleste.use_cases.dashboard.stream_flight_and_drive_stats_use_case import (
    StreamFlightAndDriveStatsUseCase,
)
from edceleste.use_cases.dashboard.stream_journal_events_usecase import (
    StreamJournalEventsUseCase,
)
from edceleste.use_cases.dashboard.stream_llm_responses_use_case import (
    StreamLLMResponsesUseCase,
)
from edceleste.use_cases.dashboard.stream_navigation_stats_use_case import (
    StreamNavigationStatsUseCase,
)
from edceleste.use_cases.dashboard.stream_ship_stats_use_case import (
    StreamShipStatsUseCase,
)
from edceleste.use_cases.dashboard.stream_station_market_use_case import (
    StreamStationMarketUseCase,
)
from edceleste.use_cases.settings.analyze_voice_sample_use_case import (
    AnalyzeVoiceSampleUseCase,
)
from edceleste.use_cases.settings.clone_voice_use_case import CloneVoiceUseCase
from edceleste.use_cases.settings.get_available_device_use_case import (
    GetAvailableDeviceUseCase,
)
from edceleste.use_cases.settings.get_available_voice_profiles_use_case import (
    GetAvailableVoiceProfilesUseCase,
)
from edceleste.use_cases.settings.get_llm_models_use_case import GetLlmModelsUseCase
from edceleste.use_cases.settings.cancel_instinct_download_use_case import (
    CancelInstinctDownloadUseCase,
)
from edceleste.use_cases.settings.download_instinct_model_use_case import (
    DownloadInstinctModelUseCase,
)
from edceleste.use_cases.settings.get_instinct_download_size_use_case import (
    GetInstinctDownloadSizeUseCase,
)
from edceleste.use_cases.settings.get_instinct_status_use_case import (
    GetInstinctStatusUseCase,
)
from edceleste.use_cases.settings.test_llm_connection_use_case import (
    TestLlmConnectionUseCase,
)
from edceleste.use_cases.settings.get_settings_use_case import GetSettingsUseCase
from edceleste.use_cases.settings.get_stt_models_use_case import GetSttModelsUseCase
from edceleste.use_cases.settings.get_stt_input_devices_use_case import (
    GetSttInputDevicesUseCase,
)
from edceleste.use_cases.settings.get_tts_voices_use_case import GetTTSVoicesUseCase
from edceleste.use_cases.settings.play_audio_file_use_case import PlayAudioFileUseCase
from edceleste.use_cases.settings.play_sample_voice_use_case import (
    PlaySampleVoiceUseCase,
)
from edceleste.use_cases.settings.preview_voice_sample_use_case import (
    PreviewVoiceSampleUseCase,
)
from edceleste.use_cases.settings.remove_voice_profile_use_case import (
    RemoveVoiceProfileUseCase,
)
from edceleste.use_cases.settings.rename_voice_profile_use_case import (
    RenameVoiceProfileUseCase,
)
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
from edceleste.use_cases.system_check.system_check_use_case import SystemCheckUseCase


# Every module with an @inject default taken from this container. A module
# missing here gets the Provide marker instead of the real object. main() and
# the e2e tests both wire this list, test_wired_modules.py keeps it complete.
MODULES_USING_PROVIDE = [
    "edceleste.ui.ui_app",
    "edceleste.ui.screens.app.widgets.app_header",
    "edceleste.ui.screens.dashboard.widgets.ship_log.widget_station_market",
    "edceleste.ui.screens.settings.widgets.stt.widget_stt_container",
    "edceleste.ui.screens.settings.widgets.system_prompts.widget_system_prompts_container",  # noqa: E501
    "edceleste.ui.screens.settings.widgets.tts.voice_clone_modal_screen",
    "edceleste.ui.screens.settings.widgets.tts.widget_chatterbox_tts_settings_vertical",  # noqa: E501
    "edceleste.ui.screens.settings.widgets.tts.widget_edge_tts_settings_vertical",
]


def _build_loaded_settings_service() -> SettingsService:
    # TODO: Add initial setting to further load it during the app settings screen
    settings_service = SettingsService()
    settings_service.load_settings()
    return settings_service


class Container(containers.DeclarativeContainer):
    # -----CONFIG-----
    config = providers.Configuration()

    # -----TOOLS-----

    settings_service = providers.Singleton(_build_loaded_settings_service)

    event_bus = providers.Singleton(EventBus)

    game_watcher_service = providers.Singleton(
        GameWatcherService,
        journal_path=settings_service.provided.get_settings.call().paths.journal_path,
        event_bus=event_bus,
        settings_handler=settings_service,
    )

    game_state_service = providers.Singleton(GameStateService, event_bus=event_bus)

    game_window = providers.Singleton(GameWindow)

    keybinds_service = providers.Singleton(
        KeybindService,
        keybinds_path=(
            settings_service.provided.get_settings.call().paths.keybindings_path
        ),
        event_bus=event_bus,
        settings_handler=settings_service,
        game_window=game_window,
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

    decision_model_download_service = providers.Singleton(DecisionModelDownloadService)

    instinct_service = providers.Singleton(
        InstinctService,
        settings_service=settings_service,
        download_service=decision_model_download_service,
    )

    voice_lab_service = providers.Singleton(
        VoiceLabService,
        settings_handler=settings_service,
    )

    tts_service = providers.Singleton(
        TTSService,
        event_bus=event_bus,
        settings_handler=settings_service,
        voice_lab_service=voice_lab_service,
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

    stream_app_header_stats_use_case = providers.Factory(
        StreamAppHeaderStatsUseCase, game_state_protocol=game_state_service
    )

    stream_journal_events_use_case = providers.Factory(
        StreamJournalEventsUseCase, game_state_reader=game_state_service
    )

    stream_navigation_stats_use_case = providers.Factory(
        StreamNavigationStatsUseCase, game_state_protocol=game_state_service
    )

    stream_flight_and_drive_stats_use_case = providers.Factory(
        StreamFlightAndDriveStatsUseCase, game_state_protocol=game_state_service
    )

    stream_ship_stats_use_case = providers.Factory(
        StreamShipStatsUseCase, game_state_protocol=game_state_service
    )

    stream_station_market_use_case = providers.Factory(
        StreamStationMarketUseCase, game_state_protocol=game_state_service
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
        game_watcher_service=game_watcher_service,
        keybinds_service=keybinds_service,
        llm_service=llm_service,
        instinct_service=instinct_service,
        event_reactions_service=event_reactions_service,
        settings_service=settings_service,
    )

    get_settings_use_case = providers.Factory(
        GetSettingsUseCase, settings_protocol=settings_service
    )

    get_tts_voices_use_case = providers.Factory(
        GetTTSVoicesUseCase, tts_protocol=tts_service
    )

    get_llm_models_use_case = providers.Factory(
        GetLlmModelsUseCase, llm_protocol=llm_service
    )

    test_llm_connection_use_case = providers.Factory(
        TestLlmConnectionUseCase, llm_protocol=llm_service
    )

    get_instinct_status_use_case = providers.Factory(
        GetInstinctStatusUseCase, instinct_protocol=instinct_service
    )

    get_instinct_download_size_use_case = providers.Factory(
        GetInstinctDownloadSizeUseCase, instinct_protocol=instinct_service
    )

    download_instinct_model_use_case = providers.Factory(
        DownloadInstinctModelUseCase, instinct_protocol=instinct_service
    )

    cancel_instinct_download_use_case = providers.Factory(
        CancelInstinctDownloadUseCase, instinct_protocol=instinct_service
    )

    clone_voice_use_case = providers.Factory(
        CloneVoiceUseCase, voice_cloning_protocol=tts_service
    )

    get_available_voice_profiles_use_case = providers.Factory(
        GetAvailableVoiceProfilesUseCase, voice_cloning_protocol=tts_service
    )

    remove_voice_profile_use_case = providers.Factory(
        RemoveVoiceProfileUseCase, voice_cloning_protocol=tts_service
    )

    rename_voice_profile_use_case = providers.Factory(
        RenameVoiceProfileUseCase, voice_cloning_protocol=tts_service
    )

    play_sample_voice_use_case = providers.Factory(
        PlaySampleVoiceUseCase, voice_cloning_protocol=tts_service
    )

    play_audio_file_use_case = providers.Factory(
        PlayAudioFileUseCase, voice_cloning_protocol=tts_service
    )

    analyze_voice_sample_use_case = providers.Factory(
        AnalyzeVoiceSampleUseCase, voice_cloning_protocol=tts_service
    )

    preview_voice_sample_use_case = providers.Factory(
        PreviewVoiceSampleUseCase, voice_cloning_protocol=tts_service
    )

    get_available_device_use_case = providers.Factory(
        GetAvailableDeviceUseCase, device_detection_protocol=tts_service
    )

    get_stt_models_use_case = providers.Factory(
        GetSttModelsUseCase, stt_protocol=stt_service
    )

    get_stt_input_devices_use_case = providers.Factory(
        GetSttInputDevicesUseCase, stt_protocol=stt_service
    )

    system_check_use_case = providers.Factory(
        SystemCheckUseCase,
        services=providers.Dict(
            settings=settings_service,
            game_watcher=game_watcher_service,
            keybinds=keybinds_service,
            llm=llm_service,
            llm__instinct=instinct_service,
            tts=tts_service,
            stt=stt_service,
            event_reactions=event_reactions_service,
        ),
    )

    # -----REPOSITORIES-----
    ed_dashboard_repository = providers.Singleton(
        EdDashboardRepository,
        stream_journal_events_usecase=stream_journal_events_use_case,
        llm_send_message_usecase=llm_send_message_use_case,
        stream_llm_responses_usecase=stream_llm_responses_use_case,
        stt_start_recording_usecase=stt_start_recording_use_case,
        stt_stop_recording_usecase=stt_stop_recording_use_case,
        get_stt_enabled_usecase=get_stt_enabled_use_case,
        stream_navigation_stats_usecase=stream_navigation_stats_use_case,
        stream_flight_and_drive_stats_usecase=stream_flight_and_drive_stats_use_case,
        stream_ship_stats_usecase=stream_ship_stats_use_case,
        stream_station_market_usecase=stream_station_market_use_case,
    )

    settings_repository = providers.Singleton(
        SettingsRepository,
        settings_load_keybinds_use_case=settings_load_keybinds_use_case,
        settings_get_keybinds_use_case=settings_get_keybinds_use_case,
        update_settings_use_case=update_settings_use_case,
        get_settings_use_case=get_settings_use_case,
        get_tts_voices_use_case=get_tts_voices_use_case,
        get_llm_models_use_case=get_llm_models_use_case,
        test_llm_connection_use_case=test_llm_connection_use_case,
        get_instinct_status_use_case=get_instinct_status_use_case,
        get_instinct_download_size_use_case=get_instinct_download_size_use_case,
        download_instinct_model_use_case=download_instinct_model_use_case,
        cancel_instinct_download_use_case=cancel_instinct_download_use_case,
        get_stt_models_use_case=get_stt_models_use_case,
        get_stt_input_devices_use_case=get_stt_input_devices_use_case,
        clone_voice_use_case=clone_voice_use_case,
        get_available_voice_profiles_use_case=get_available_voice_profiles_use_case,
        remove_voice_profile_use_case=remove_voice_profile_use_case,
        rename_voice_profile_use_case=rename_voice_profile_use_case,
        play_sample_voice_use_case=play_sample_voice_use_case,
        play_audio_file_use_case=play_audio_file_use_case,
        analyze_voice_sample_use_case=analyze_voice_sample_use_case,
        preview_voice_sample_use_case=preview_voice_sample_use_case,
        get_available_device_use_case=get_available_device_use_case,
    )
    system_check_repository = providers.Singleton(
        SystemCheckRepository, system_check_use_case=system_check_use_case
    )

    app_header_repository = providers.Singleton(
        AppHeaderRepository,
        stream_app_header_stats_usecase=stream_app_header_stats_use_case,
    )
