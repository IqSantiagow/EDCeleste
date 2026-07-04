from collections.abc import AsyncGenerator
import unittest

from services.models.llm_response import LLMStatus
from use_cases.dashboard.stream_llm_state_use_case import StreamLLMStateUseCase


async def _async_gen(items) -> AsyncGenerator:
    for item in items:
        yield item


class FakeLLMProtocol:
    def __init__(self, statuses=None):
        self._statuses = statuses or []

    async def stream_llm_status(self):
        async for status in _async_gen(self._statuses):
            yield status


class TestStreamLLMStateUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_through_statuses_in_order(self):
        llm = FakeLLMProtocol(statuses=[LLMStatus.THINKING, LLMStatus.IDLE])
        use_case = StreamLLMStateUseCase(llm)  # type: ignore

        results = [status async for status in use_case()]

        self.assertEqual(results, [LLMStatus.THINKING, LLMStatus.IDLE])

    async def test_should_complete_when_stream_is_empty(self):
        llm = FakeLLMProtocol(statuses=[])
        use_case = StreamLLMStateUseCase(llm)  # type: ignore

        results = [status async for status in use_case()]

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
