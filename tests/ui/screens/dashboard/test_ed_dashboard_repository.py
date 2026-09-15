import unittest

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
            llm_send_message_usecase=None,  # type: ignore
            stream_llm_responses_usecase=None,  # type: ignore
            stt_start_recording_usecase=None,  # type: ignore
            stt_stop_recording_usecase=None,  # type: ignore
            get_stt_enabled_usecase=FakeGetSttEnabledUseCase(enabled),  # type: ignore
            stream_navigation_stats_usecase=None,  # type: ignore
            stream_flight_and_drive_stats_usecase=None,  # type: ignore
            stream_ship_stats_usecase=None,  # type: ignore
        )

    def test_is_stt_enabled_returns_true_when_use_case_returns_true(self):
        repository = self._make_repository(enabled=True)

        self.assertTrue(repository.is_stt_enabled())

    def test_is_stt_enabled_returns_false_when_use_case_returns_false(self):
        repository = self._make_repository(enabled=False)

        self.assertFalse(repository.is_stt_enabled())


class FakeStreamUseCase:
    def __init__(self, stream):
        self._stream = stream

    def __call__(self):
        return self._stream


class TestEdDashboardRepositoryStatsStreams(unittest.TestCase):
    def _make_repository(self, **stats_use_cases) -> EdDashboardRepository:
        use_cases = dict(
            stream_journal_events_usecase=None,
            llm_send_message_usecase=None,
            stream_llm_responses_usecase=None,
            stt_start_recording_usecase=None,
            stt_stop_recording_usecase=None,
            get_stt_enabled_usecase=None,
            stream_navigation_stats_usecase=None,
            stream_flight_and_drive_stats_usecase=None,
            stream_ship_stats_usecase=None,
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


if __name__ == "__main__":
    unittest.main()
