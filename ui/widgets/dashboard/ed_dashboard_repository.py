import asyncio
from collections.abc import AsyncGenerator

from services.models.llm_response import LLMStatus
from ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)
from ui.widgets.dashboard.view_models.journal_log_view_model import JournalLogViewModel
from ui.widgets.dashboard.view_models.llm_jrnl_healthcheck_view_model import (
    LlmJrnlHealthCheckViewModel,
)
from use_cases.dashboard.journal_get_healtcheck_usecase import (
    JournalGetHealthCheckUseCase,
)
from use_cases.dashboard.llm_get_healthcheck_usecase import LlmGetHealthCheckUseCase
from use_cases.dashboard.llm_send_message_use_case import LLMSendMessageUseCase
from use_cases.dashboard.stream_dashboard_stats_usecase import (
    StreamDashboardStatsUseCase,
)
from ui.widgets.dashboard.view_models.dashboard_stats_view_model import (
    DashboardStatsViewModel,
)
from use_cases.dashboard.stream_journal_events_usecase import StreamJournalEventsUseCase
from use_cases.dashboard.stream_llm_responses_use_case import StreamLLMResponsesUseCase
from use_cases.dashboard.stream_llm_state_use_case import StreamLLMStateUseCase
from use_cases.dashboard.stt_transcribe_audio_use_case import SttTranscribeAudioUseCase
from use_cases.dashboard.get_stt_enabled_use_case import GetSttEnabledUseCase


class EdDashboardRepository:
    def __init__(
        self,
        stream_dashboard_stats_usecase: StreamDashboardStatsUseCase,
        journal_get_healthcheck_usecase: JournalGetHealthCheckUseCase,
        llm_get_healthcheck_usecase: LlmGetHealthCheckUseCase,
        stream_journal_events_usecase: StreamJournalEventsUseCase,
        stream_llm_state_usecase: StreamLLMStateUseCase,
        llm_send_message_usecase: LLMSendMessageUseCase,
        stream_llm_responses_usecase: StreamLLMResponsesUseCase,
        stt_transcribe_audio_usecase: SttTranscribeAudioUseCase,
        get_stt_enabled_usecase: GetSttEnabledUseCase,
    ) -> None:
        self.stream_dashboard_stats_usecase = stream_dashboard_stats_usecase
        self.stream_journal_events_usecase = stream_journal_events_usecase
        self.journal_get_healthcheck_usecase = journal_get_healthcheck_usecase
        self.llm_get_healthcheck_usecase = llm_get_healthcheck_usecase
        self.stream_llm_state_usecase = stream_llm_state_usecase
        self.llm_send_message_usecase = llm_send_message_usecase
        self.stream_llm_responses_usecase = stream_llm_responses_usecase
        self.stt_transcribe_audio_usecase = stt_transcribe_audio_usecase
        self.get_stt_enabled_usecase = get_stt_enabled_usecase

    def stream_dashboard_stats(self) -> AsyncGenerator[DashboardStatsViewModel, None]:
        return self.stream_dashboard_stats_usecase()

    async def stream_healthcheck(
        self,
    ) -> AsyncGenerator[LlmJrnlHealthCheckViewModel, None]:
        hc_queue = asyncio.Queue()

        async def llm_healthcheck_task():
            while True:
                async for llm_hc in self.llm_get_healthcheck_usecase():
                    await hc_queue.put(("llm", llm_hc))

        async def journal_healthcheck_task():
            while True:
                async for journal_hc in self.journal_get_healthcheck_usecase():
                    await hc_queue.put(("journal", journal_hc))

        def _on_task_done(task: asyncio.Task) -> None:
            if not task.cancelled() and (exc := task.exception()) is not None:
                hc_queue.put_nowait(("error", exc))

        tasks = [
            asyncio.create_task(llm_healthcheck_task()),
            asyncio.create_task(journal_healthcheck_task()),
        ]
        for task in tasks:
            task.add_done_callback(_on_task_done)

        try:
            old_llm_hc = False
            old_journal_hc = False
            while True:
                source, hc = await hc_queue.get()
                if source == "error":
                    raise hc
                if source == "llm":
                    old_llm_hc = hc
                elif source == "journal":
                    old_journal_hc = hc
                yield LlmJrnlHealthCheckViewModel(
                    llm_healthcheck=old_llm_hc, journal_healthcheck=old_journal_hc
                )
        finally:
            for task in tasks:
                task.cancel()

    def stream_journal_events(self) -> AsyncGenerator[JournalLogViewModel, None]:
        return self.stream_journal_events_usecase()

    def stream_llm_state(self) -> AsyncGenerator[LLMStatus, None]:
        return self.stream_llm_state_usecase()

    async def send_message_to_llm(self, message: str) -> None:
        await self.llm_send_message_usecase(message)

    def stream_llm_responses(self) -> AsyncGenerator[CommsMessageViewModel, None]:
        return self.stream_llm_responses_usecase()

    def transcribe_audio(self, audio_path: str) -> str | None:
        return self.stt_transcribe_audio_usecase(audio_path)

    def is_stt_enabled(self) -> bool:
        return self.get_stt_enabled_usecase()
