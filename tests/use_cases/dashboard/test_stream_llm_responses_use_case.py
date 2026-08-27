import unittest

from services.models.message_block import AgentText, Thinking, ToolCall, ToolResult
from services.models.llm_status import LLMStatus
from ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)
from use_cases.dashboard.stream_llm_responses_use_case import StreamLLMResponsesUseCase


class FakeLLMProtocol:
    def __init__(self, items=None, error=None):
        self._items = items or []
        self._error = error

    async def consume_llm_queue(self):
        for item in self._items:
            yield item
        if self._error is not None:
            raise self._error


class TestStreamLLMResponsesUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_pass_status_through_and_map_only_visible_blocks(self):
        llm = FakeLLMProtocol(
            items=[
                LLMStatus.THINKING,
                AgentText(content="Hello pilot"),
                Thinking(content="hmm"),
                ToolResult(content="ok", is_error=False),
                LLMStatus.IDLE,
            ]
        )
        use_case = StreamLLMResponsesUseCase(llm)  # type: ignore

        results = [item async for item in use_case()]

        self.assertEqual(
            results,
            [
                LLMStatus.THINKING,
                CommsMessageViewModel(content="Hello pilot", entry_type="llm-response"),
                LLMStatus.IDLE,
            ],
        )

    async def test_should_map_tool_call_and_failed_tool_result(self):
        llm = FakeLLMProtocol(
            items=[
                ToolCall(
                    tool_readable_name="Perform game action",
                    tool_name="perform_game_action",
                    param_name="action",
                    input={"action": "Boost"},
                ),
                ToolResult(content="keybind missing", is_error=True),
            ]
        )
        use_case = StreamLLMResponsesUseCase(llm)  # type: ignore

        results = [item async for item in use_case()]

        self.assertEqual(
            results,
            [
                CommsMessageViewModel(
                    content="Perform game action -> Boost",
                    entry_type="llm-action",
                ),
                CommsMessageViewModel(
                    content="keybind missing", entry_type="llm-error"
                ),
            ],
        )

    async def test_should_complete_when_stream_is_empty(self):
        llm = FakeLLMProtocol(items=[])
        use_case = StreamLLMResponsesUseCase(llm)  # type: ignore

        results = [item async for item in use_case()]

        self.assertEqual(results, [])

    async def test_should_propagate_exception_from_stream(self):
        llm = FakeLLMProtocol(items=[], error=RuntimeError("boom"))
        use_case = StreamLLMResponsesUseCase(llm)  # type: ignore

        with self.assertRaises(RuntimeError):
            async for _ in use_case():
                pass


if __name__ == "__main__":
    unittest.main()
