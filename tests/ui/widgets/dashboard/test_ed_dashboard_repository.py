import unittest

from edceleste.ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository


class FakeGetSttEnabledUseCase:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def __call__(self) -> bool:
        return self._enabled


class TestEdDashboardRepositoryIsSttEnabled(unittest.TestCase):
    def _make_repository(self, enabled: bool) -> EdDashboardRepository:
        return EdDashboardRepository(
            stream_dashboard_stats_usecase=None,  # type: ignore
            stream_journal_events_usecase=None,  # type: ignore
            llm_send_message_usecase=None,  # type: ignore
            stream_llm_responses_usecase=None,  # type: ignore
            stt_start_recording_usecase=None,  # type: ignore
            stt_stop_recording_usecase=None,  # type: ignore
            get_stt_enabled_usecase=FakeGetSttEnabledUseCase(enabled),  # type: ignore
        )

    def test_is_stt_enabled_returns_true_when_use_case_returns_true(self):
        repository = self._make_repository(enabled=True)

        self.assertTrue(repository.is_stt_enabled())

    def test_is_stt_enabled_returns_false_when_use_case_returns_false(self):
        repository = self._make_repository(enabled=False)

        self.assertFalse(repository.is_stt_enabled())


if __name__ == "__main__":
    unittest.main()
