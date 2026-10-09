from collections.abc import AsyncGenerator

from edceleste.ui.screens.dashboard.view_models.game_stats_view_model import (
    FlightAndDriveViewModel,
    NavigationStatsViewModel,
    ShipStatsViewModel,
)
from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    JournalLogViewModel,
)
from edceleste.use_cases.dashboard.llm_send_message_use_case import (
    LLMSendMessageUseCase,
)
from edceleste.use_cases.dashboard.stream_flight_and_drive_stats_use_case import (
    StreamFlightAndDriveStatsUseCase,
)
from edceleste.use_cases.dashboard.stream_journal_events_usecase import (
    StreamJournalEventsUseCase,
)
from edceleste.use_cases.dashboard.stream_llm_responses_use_case import (
    CommsStreamItem,
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
from edceleste.ui.screens.dashboard.view_models.station_market_view_model import (
    StationMarketViewModel,
)
from edceleste.use_cases.dashboard.stt_start_recording_use_case import (
    SttStartRecordingUseCase,
)
from edceleste.use_cases.dashboard.stt_stop_recording_use_case import (
    SttStopRecordingUseCase,
)
from edceleste.use_cases.dashboard.get_stt_enabled_use_case import GetSttEnabledUseCase


class EdDashboardRepository:
    def __init__(
        self,
        stream_journal_events_usecase: StreamJournalEventsUseCase,
        llm_send_message_usecase: LLMSendMessageUseCase,
        stream_llm_responses_usecase: StreamLLMResponsesUseCase,
        stt_start_recording_usecase: SttStartRecordingUseCase,
        stt_stop_recording_usecase: SttStopRecordingUseCase,
        get_stt_enabled_usecase: GetSttEnabledUseCase,
        stream_navigation_stats_usecase: StreamNavigationStatsUseCase,
        stream_flight_and_drive_stats_usecase: StreamFlightAndDriveStatsUseCase,
        stream_ship_stats_usecase: StreamShipStatsUseCase,
        stream_station_market_usecase: StreamStationMarketUseCase,
    ) -> None:
        """The dashboard's only way to the services. Every method below just
        calls one use case, so the widgets never know a use case or a
        service."""
        self.stream_journal_events_usecase = stream_journal_events_usecase
        self.llm_send_message_usecase = llm_send_message_usecase
        self.stream_llm_responses_usecase = stream_llm_responses_usecase
        self.stt_start_recording_usecase = stt_start_recording_usecase
        self.stt_stop_recording_usecase = stt_stop_recording_usecase
        self.get_stt_enabled_usecase = get_stt_enabled_usecase
        self.stream_navigation_stats_usecase = stream_navigation_stats_usecase
        self.stream_flight_and_drive_stats_usecase = (
            stream_flight_and_drive_stats_usecase
        )
        self.stream_ship_stats_usecase = stream_ship_stats_usecase
        self.stream_station_market_usecase = stream_station_market_usecase

    def stream_journal_events(self) -> AsyncGenerator[JournalLogViewModel, None]:
        """Never ends. One ship log row for every new journal event, older
        events are not replayed. DashboardScreen is the only reader."""
        return self.stream_journal_events_usecase()

    def send_message_to_llm(self, message: str) -> None:
        """Only puts the message in the LLM queue and returns at once. The
        reply comes later out of stream_llm_responses()."""
        self.llm_send_message_usecase(message)

    def stream_llm_responses(self) -> AsyncGenerator[CommsStreamItem, None]:
        """Never ends. Gives LLMStatus items (thinking / idle) and COMMS
        messages for every queued request. Must have only one reader, the
        DashboardScreen worker, because it empties the LLM queue."""
        return self.stream_llm_responses_usecase()

    def start_recording(self) -> None:
        """Opens the microphone and returns at once. Raises SttException when
        STT is disabled or a recording already runs."""
        self.stt_start_recording_usecase()

    def stop_recording_and_transcribe(self) -> str | None:
        """Stops the microphone AND transcribes the audio, so it is slow and
        blocking. Returns the spoken text, or None when nothing was heard.
        Raises SttException when no recording runs."""
        return self.stt_stop_recording_usecase()

    def is_stt_enabled(self) -> bool:
        """The STT service's in-memory flag, the settings file is not read."""
        return self.get_stt_enabled_usecase()

    def stream_navigation_stats(self) -> AsyncGenerator[NavigationStatsViewModel, None]:
        """Never ends. The current stats at once, then fresh ones after every
        Status.json or Market.json event. Read by WidgetNavigationStats."""
        return self.stream_navigation_stats_usecase()

    def stream_flight_and_drive_stats(
        self,
    ) -> AsyncGenerator[FlightAndDriveViewModel, None]:
        """Never ends. The current stats at once, then fresh ones after every
        Status.json or Market.json event. Read by WidgetFlightAndDriveStats."""
        return self.stream_flight_and_drive_stats_usecase()

    def stream_ship_stats(self) -> AsyncGenerator[ShipStatsViewModel, None]:
        """Never ends. The current stats at once, then fresh ones after every
        Status.json or Market.json event. Read by WidgetShipStats."""
        return self.stream_ship_stats_usecase()

    def stream_station_market(self) -> AsyncGenerator[StationMarketViewModel, None]:
        """Never ends. The current market card at once, then a new one only
        after docking, undocking, Location or a new Market.json. Read by
        WidgetStationMarket."""
        return self.stream_station_market_usecase()
