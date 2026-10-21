import unittest
from unittest.mock import Mock

from edceleste.ui.screens.dashboard.ed_dashboard_repository import EdDashboardRepository


class FakeGetSttEnabledUseCase:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def __call__(self) -> bool:
        return self._enabled


class TestEdDashboardRepositoryIsSttEnabled(unittest.TestCase):
    def _make_repository(self, enabled: bool) -> EdDashboardRepository:
        return EdDashboardRepository(
            stream_journal_events_usecase=None,  # type: ignore
            send_pilot_message_usecase=None,  # type: ignore
            stream_llm_responses_usecase=None,  # type: ignore
            stt_start_recording_usecase=None,  # type: ignore
            stt_stop_recording_usecase=None,  # type: ignore
            get_stt_enabled_usecase=FakeGetSttEnabledUseCase(enabled),  # type: ignore
            stream_stt_transcriptions_usecase=None,  # type: ignore
            stream_navigation_stats_usecase=None,  # type: ignore
            stream_flight_and_drive_stats_usecase=None,  # type: ignore
            stream_ship_stats_usecase=None,  # type: ignore
            stream_station_market_usecase=None,  # type: ignore
        )

    def test_is_stt_enabled_returns_true_when_use_case_returns_true(self):
        repository = self._make_repository(enabled=True)

        self.assertTrue(repository.is_stt_enabled())

    def test_is_stt_enabled_returns_false_when_use_case_returns_false(self):
        repository = self._make_repository(enabled=False)

        self.assertFalse(repository.is_stt_enabled())


class FakeSendPilotMessageUseCase:
    def __init__(self):
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)


class TestEdDashboardRepositorySendPilotMessage(unittest.TestCase):
    def test_send_pilot_message_calls_its_use_case_with_the_message(self):
        use_case = FakeSendPilotMessageUseCase()
        repository = EdDashboardRepository(
            stream_journal_events_usecase=None,  # type: ignore
            send_pilot_message_usecase=use_case,  # type: ignore
            stream_llm_responses_usecase=None,  # type: ignore
            stt_start_recording_usecase=None,  # type: ignore
            stt_stop_recording_usecase=None,  # type: ignore
            get_stt_enabled_usecase=None,  # type: ignore
            stream_stt_transcriptions_usecase=None,  # type: ignore
            stream_navigation_stats_usecase=None,  # type: ignore
            stream_flight_and_drive_stats_usecase=None,  # type: ignore
            stream_ship_stats_usecase=None,  # type: ignore
            stream_station_market_usecase=None,  # type: ignore
        )

        repository.send_pilot_message("deploy landing gear")

        self.assertEqual(use_case.messages, ["deploy landing gear"])


class FakeStreamUseCase:
    def __init__(self, stream):
        self._stream = stream

    def __call__(self):
        return self._stream


class TestEdDashboardRepositoryStatsStreams(unittest.TestCase):
    def _make_repository(self, **stats_use_cases) -> EdDashboardRepository:
        use_cases = dict(
            stream_journal_events_usecase=None,
            send_pilot_message_usecase=None,
            stream_llm_responses_usecase=None,
            stt_start_recording_usecase=None,
            stt_stop_recording_usecase=None,
            get_stt_enabled_usecase=None,
            stream_stt_transcriptions_usecase=None,
            stream_navigation_stats_usecase=None,
            stream_flight_and_drive_stats_usecase=None,
            stream_ship_stats_usecase=None,
            stream_station_market_usecase=None,
        )
        use_cases.update(stats_use_cases)
        return EdDashboardRepository(**use_cases)  # type: ignore

    def test_stream_navigation_stats_returns_stream_from_its_use_case(self):
        stream = object()
        repository = self._make_repository(
            stream_navigation_stats_usecase=FakeStreamUseCase(stream)
        )

        self.assertIs(repository.stream_navigation_stats(), stream)

    def test_stream_flight_and_drive_stats_returns_stream_from_its_use_case(self):
        stream = object()
        repository = self._make_repository(
            stream_flight_and_drive_stats_usecase=FakeStreamUseCase(stream)
        )

        self.assertIs(repository.stream_flight_and_drive_stats(), stream)

    def test_stream_ship_stats_returns_stream_from_its_use_case(self):
        stream = object()
        repository = self._make_repository(
            stream_ship_stats_usecase=FakeStreamUseCase(stream)
        )

        self.assertIs(repository.stream_ship_stats(), stream)

    def test_stream_station_market_returns_stream_from_its_use_case(self):
        stream = object()
        repository = self._make_repository(
            stream_station_market_usecase=FakeStreamUseCase(stream)
        )

        self.assertIs(repository.stream_station_market(), stream)


class TestEdDashboardRepositorySttFlow(unittest.TestCase):
    def _make_repository(self, **stt_use_cases) -> EdDashboardRepository:
        use_cases = dict(
            stream_journal_events_usecase=None,
            send_pilot_message_usecase=None,
            stream_llm_responses_usecase=None,
            stt_start_recording_usecase=None,
            stt_stop_recording_usecase=None,
            get_stt_enabled_usecase=None,
            stream_stt_transcriptions_usecase=None,
            stream_navigation_stats_usecase=None,
            stream_flight_and_drive_stats_usecase=None,
            stream_ship_stats_usecase=None,
            stream_station_market_usecase=None,
        )
        use_cases.update(stt_use_cases)
        return EdDashboardRepository(**use_cases)  # type: ignore

    def test_stream_stt_transcriptions_returns_stream_from_its_use_case(self):
        stream = object()
        repository = self._make_repository(
            stream_stt_transcriptions_usecase=FakeStreamUseCase(stream)
        )

        self.assertIs(repository.stream_stt_transcriptions(), stream)

    def test_stop_recording_and_transcribe_calls_its_use_case_and_returns_nothing(
        self,
    ):
        use_case = Mock(return_value="text that must not leak out")
        repository = self._make_repository(stt_stop_recording_usecase=use_case)

        result = repository.stop_recording_and_transcribe()

        use_case.assert_called_once_with()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
