from collections.abc import AsyncGenerator
import unittest

from services.models.llm_response import LLMResponse
from use_cases.dashboard.stream_llm_responses_use_case import StreamLLMResponsesUseCase


async def _async_gen(items) -> AsyncGenerator:
    for item in items:
        yield item


class FakeLLMProtocol:
    def __init__(self, responses=None, error=None):
        self._responses = responses or []
        self._error = error

    async def stream_responses(self):
        async for response in _async_gen(self._responses):
            yield response
        if self._error is not None:
            raise self._error


def _response(text: str) -> LLMResponse:
    return LLMResponse(message=text)


class TestStreamLLMResponsesUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_map_llm_response_to_view_model(self):
        llm = FakeLLMProtocol(responses=[_response("Hello pilot")])
        use_case = StreamLLMResponsesUseCase(llm)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].content, "Hello pilot")
        self.assertFalse(results[0].is_user_message)
        self.assertFalse(results[0].is_action)

    async def test_should_yield_multiple_responses_in_order(self):
        llm = FakeLLMProtocol(
            responses=[_response("one"), _response("two"), _response("three")]
        )
        use_case = StreamLLMResponsesUseCase(llm)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(
            [view_model.content for view_model in results], ["one", "two", "three"]
        )

    async def test_should_complete_when_stream_is_empty(self):
        llm = FakeLLMProtocol(responses=[])
        use_case = StreamLLMResponsesUseCase(llm)  # type: ignore

        results = [view_model async for view_model in use_case()]

        self.assertEqual(results, [])

    async def test_should_propagate_exception_from_stream(self):
        llm = FakeLLMProtocol(responses=[], error=RuntimeError("boom"))
        use_case = StreamLLMResponsesUseCase(llm)  # type: ignore

        with self.assertRaises(RuntimeError):
            async for _ in use_case():
                pass


if __name__ == "__main__":
    unittest.main()
