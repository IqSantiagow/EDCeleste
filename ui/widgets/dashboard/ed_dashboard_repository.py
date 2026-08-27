from collections.abc import AsyncGenerator

from ui.widgets.dashboard.view_models.journal_log_view_model import JournalLogViewModel
from use_cases.dashboard.llm_send_message_use_case import LLMSendMessageUseCase
from use_cases.dashboard.stream_dashboard_stats_usecase import (
    StreamDashboardStatsUseCase,
)
from ui.widgets.dashboard.view_models.dashboard_stats_view_model import (
    DashboardStatsViewModel,
)
from use_cases.dashboard.stream_journal_events_usecase import StreamJournalEventsUseCase
from use_cases.dashboard.stream_llm_responses_use_case import (
    CommsStreamItem,
    StreamLLMResponsesUseCase,
)
from use_cases.dashboard.stt_start_recording_use_case import SttStartRecordingUseCase
from use_cases.dashboard.stt_stop_recording_use_case import SttStopRecordingUseCase
from use_cases.dashboard.get_stt_enabled_use_case import GetSttEnabledUseCase


class EdDashboardRepository:
    def __init__(
        self,
        stream_dashboard_stats_usecase: StreamDashboardStatsUseCase,
        stream_journal_events_usecase: StreamJournalEventsUseCase,
        llm_send_message_usecase: LLMSendMessageUseCase,
        stream_llm_responses_usecase: StreamLLMResponsesUseCase,
        stt_start_recording_usecase: SttStartRecordingUseCase,
        stt_stop_recording_usecase: SttStopRecordingUseCase,
        get_stt_enabled_usecase: GetSttEnabledUseCase,
    ) -> None:
        self.stream_dashboard_stats_usecase = stream_dashboard_stats_usecase
        self.stream_journal_events_usecase = stream_journal_events_usecase
        self.llm_send_message_usecase = llm_send_message_usecase
        self.stream_llm_responses_usecase = stream_llm_responses_usecase
        self.stt_start_recording_usecase = stt_start_recording_usecase
        self.stt_stop_recording_usecase = stt_stop_recording_usecase
        self.get_stt_enabled_usecase = get_stt_enabled_usecase

    def stream_dashboard_stats(self) -> AsyncGenerator[DashboardStatsViewModel, None]:
        return self.stream_dashboard_stats_usecase()

    def stream_journal_events(self) -> AsyncGenerator[JournalLogViewModel, None]:
        return self.stream_journal_events_usecase()

    def send_message_to_llm(self, message: str) -> None:
        self.llm_send_message_usecase(message)

    def stream_llm_responses(self) -> AsyncGenerator[CommsStreamItem, None]:
        return self.stream_llm_responses_usecase()

    def start_recording(self) -> None:
        self.stt_start_recording_usecase()

    def stop_recording(self) -> str | None:
        return self.stt_stop_recording_usecase()

    def is_stt_enabled(self) -> bool:
        return self.get_stt_enabled_usecase()
