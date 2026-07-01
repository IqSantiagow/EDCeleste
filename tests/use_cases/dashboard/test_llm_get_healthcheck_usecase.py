import unittest
from unittest.mock import Mock, patch

from use_cases.dashboard.llm_get_healthcheck_usecase import (
    POLL_INTERVAL_SECONDS,
    LlmGetHealthCheckUseCase,
)


class TestLlmGetHealthCheckUseCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        sleep_patcher = patch(
            "use_cases.dashboard.llm_get_healthcheck_usecase.asyncio.sleep"
        )
        self.mock_sleep = sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    async def test_should_yield_healthcheck_value_from_llm_protocol(self):
        llm_protocol = Mock()
        llm_protocol.get_llm_healthcheck.return_value = True
        use_case = LlmGetHealthCheckUseCase(llm_protocol)  # type: ignore

        gen = use_case()
        result = await gen.__anext__()

        self.assertTrue(result)

    async def test_should_poll_llm_protocol_on_each_iteration_with_configured_interval(
        self,
    ):
        llm_protocol = Mock()
        llm_protocol.get_llm_healthcheck.side_effect = [True, False, True]
        use_case = LlmGetHealthCheckUseCase(llm_protocol)  # type: ignore

        gen = use_case()
        results = [await gen.__anext__() for _ in range(3)]

        self.assertEqual(results, [True, False, True])
        self.mock_sleep.assert_called_with(POLL_INTERVAL_SECONDS)
        self.assertEqual(self.mock_sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
