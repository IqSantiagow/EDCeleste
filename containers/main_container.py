from dependency_injector import containers, providers

from config.config import AppConfig
from projection.game_state_service import GameStateService
from services.event_bus import EventBus
from services.journal_watcher_service import JournalWatcherService
from services.llm_service import LLMService
from services.stubs.journal_watcher_service_stub import JournalWatcherServiceStub
from ui.widgets.dashboard.ed_dashboard_presenter import EdDashboardPresenter
from use_cases.dashboard.load_dashboard_stats_usecase import LoadDashboardStatsUseCase
from use_cases.dashboard.stream_dashboard_stats_usecase import (
    StreamDashboardStatsUseCase,
)


class Container(containers.DeclarativeContainer):
    config = providers.Configuration(pydantic_settings=[AppConfig()])  # type: ignore

    llm_service = providers.Singleton(LLMService, api_key=config.llm.anthropic_api_key)

    event_bus = providers.Singleton(EventBus)

    journal_watcher_service = providers.Singleton(
        JournalWatcherService, journal_path=config.ed.main_path, event_bus=event_bus
    )

    journal_watcher_service_stub = providers.Singleton(
        JournalWatcherServiceStub, event_bus=event_bus
    )

    game_state_service = providers.Singleton(GameStateService, event_bus=event_bus)

    load_dashboard_stats_use_case = providers.Factory(
        LoadDashboardStatsUseCase, game_state_reader=game_state_service
    )

    stream_dashboard_stats_use_case = providers.Factory(
        StreamDashboardStatsUseCase, game_state_reader=game_state_service
    )

    ed_dashboard_presenter = providers.Singleton(
        EdDashboardPresenter,
        load_dashboard_stats_usecase=load_dashboard_stats_use_case,
        stream_dashboard_stats_usecase=stream_dashboard_stats_use_case,
    )
