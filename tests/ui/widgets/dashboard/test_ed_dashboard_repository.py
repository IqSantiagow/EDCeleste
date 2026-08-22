import asyncio
import unittest

from ui.widgets.dashboard.ed_dashboard_repository import EdDashboardRepository

ANEXT_TIMEOUT_SECONDS = 1


class FakeHealthcheckUseCase:
    """Async-generator fake: yields the given values once, then hangs forever
    (mirrors the real use cases, which poll indefinitely). `values=None` means
    the source never emits anything."""

    def __init__(self, values=None):
        self._values = values

    async def __call__(self):
        if self._values is None:
            await asyncio.Event().wait()
            return
        for value in self._values:
            yield value
        await asyncio.Event().wait()


class TestEdDashboardRepositoryStreamHealthcheck(unittest.IsolatedAsyncioTestCase):
    def _make_repository(self, journal_values=None, llm_values=None):
        return EdDashboardRepository(
            stream_dashboard_stats_usecase=None,  # type: ignore
            journal_get_healthcheck_usecase=FakeHealthcheckUseCase(journal_values),  # type: ignore
            llm_get_healthcheck_usecase=FakeHealthcheckUseCase(llm_values),  # type: ignore
            stream_journal_events_usecase=None,  # type: ignore
            stream_llm_state_usecase=None,  # type: ignore
            llm_send_message_usecase=None,  # type: ignore
            stream_llm_responses_usecase=None,  # type: ignore
            stt_start_recording_usecase=None,  # type: ignore
            stt_stop_recording_usecase=None,  # type: ignore
            get_stt_enabled_usecase=None,  # type: ignore
        )

    async def _next(self, gen):
        return await asyncio.wait_for(gen.__anext__(), timeout=ANEXT_TIMEOUT_SECONDS)

    async def test_should_yield_update_when_only_journal_source_emits(self):
        repository = self._make_repository(journal_values=[True], llm_values=None)

        result = await self._next(repository.stream_healthcheck())

        self.assertTrue(result.journal_healthcheck)
        self.assertFalse(result.llm_healthcheck)

    async def test_should_yield_update_when_only_llm_source_emits(self):
        repository = self._make_repository(journal_values=None, llm_values=[True])

        result = await self._next(repository.stream_healthcheck())

        self.assertTrue(result.llm_healthcheck)
        self.assertFalse(result.journal_healthcheck)

    async def test_should_combine_updates_from_both_sources(self):
        repository = self._make_repository(journal_values=[True], llm_values=[True])

        gen = repository.stream_healthcheck()
        await self._next(gen)
        second_result = await self._next(gen)

        self.assertTrue(second_result.journal_healthcheck)
        self.assertTrue(second_result.llm_healthcheck)

    async def test_should_preserve_last_known_value_from_other_source(self):
        repository = self._make_repository(
            journal_values=[True, False], llm_values=None
        )

        gen = repository.stream_healthcheck()
        first_result = await self._next(gen)
        second_result = await self._next(gen)

        self.assertTrue(first_result.journal_healthcheck)
        self.assertFalse(first_result.llm_healthcheck)
        self.assertFalse(second_result.journal_healthcheck)
        self.assertFalse(second_result.llm_healthcheck)


class FakeGetSttEnabledUseCase:
    """Callable fake mirroring GetSttEnabledUseCase: returns a fixed flag."""

    def __init__(self, enabled: bool):
        self._enabled = enabled

    def __call__(self) -> bool:
        return self._enabled


class TestEdDashboardRepositoryIsSttEnabled(unittest.TestCase):
    def _make_repository(self, enabled: bool) -> EdDashboardRepository:
        return EdDashboardRepository(
            stream_dashboard_stats_usecase=None,  # type: ignore
            journal_get_healthcheck_usecase=None,  # type: ignore
            llm_get_healthcheck_usecase=None,  # type: ignore
            stream_journal_events_usecase=None,  # type: ignore
            stream_llm_state_usecase=None,  # type: ignore
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
