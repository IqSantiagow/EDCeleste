import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import anthropic
import httpx
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from services.event_bus import EventBus
from services.llm_service import SYSTEM_PROMPT, LLMService
from services.models.keybinds_model import EdAction
from services.models.llm_response import LLMStatus


class LLMServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # LLMService builds a LangChain agent in __init__; patch the factory so
        # no real agent (or network call) is created and we can drive `ainvoke`.
        agent_patcher = patch("services.llm_service.create_agent")
        self.mock_create_agent = agent_patcher.start()
        self.addCleanup(agent_patcher.stop)

        self.mock_agent = self.mock_create_agent.return_value
        self.mock_agent.ainvoke = AsyncMock(
            side_effect=[
                {"structured_response": {"message": {"message": "Test output 1"}}},
                {"structured_response": {"message": {"message": "Test output 2"}}},
            ]
        )

        self.test_game_state = "Test game state"
        self.event_bus = EventBus()
        self.llm_service = LLMService(api_key="", event_bus=self.event_bus)

    async def test_should_stream_the_received_message_to_subscribers(self):
        stream = self.llm_service.stream_responses()
        # Prime the subscriber: pulling once registers its queue before we send.
        # A late subscriber would miss the response (pub/sub, no replay).
        next_response = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await self.llm_service.send_message("Test message", self.test_game_state)

        response = await next_response
        self.assertEqual(response.message.message, "Test output 1")
        await stream.aclose()

    async def test_should_add_message_to_conv_history(self):
        message1 = "Test message 1"
        message2 = "Test message 2"

        await self.llm_service.send_message(message1, self.test_game_state)
        await self.llm_service.send_message(message2, self.test_game_state)

        conversation = self.llm_service.conversation
        self.assertIn(HumanMessage(content=message1), conversation)
        self.assertIn(HumanMessage(content=message2), conversation)
        self.assertIn(AIMessage(content="Test output 1"), conversation)
        self.assertIn(AIMessage(content="Test output 2"), conversation)

    async def test_should_pass_system_prompt_and_game_state_to_the_agent(self):
        await self.llm_service.send_message("Test message 1", self.test_game_state)

        self.assertEqual(
            self.mock_create_agent.call_args.kwargs["system_prompt"], SYSTEM_PROMPT
        )

        self.assertIn(
            self.test_game_state,
            self.mock_agent.ainvoke.call_args.args[0]["messages"][0].content,
        )

    def test_should_return_true_when_token_count_succeeds(self):
        with patch(
            "langchain_anthropic.ChatAnthropic.get_num_tokens_from_messages"
        ) as mock_get_num_tokens:
            mock_get_num_tokens.return_value = 42

            result = self.llm_service.get_llm_healthcheck()

            self.assertTrue(result)

    def test_should_return_false_when_anthropic_api_error_is_raised(self):
        api_error = anthropic.APIError(
            "boom",
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            body=None,
        )

        with patch(
            "langchain_anthropic.ChatAnthropic.get_num_tokens_from_messages"
        ) as mock_get_num_tokens:
            mock_get_num_tokens.side_effect = api_error

            result = self.llm_service.get_llm_healthcheck()

            self.assertFalse(result)

    async def test_should_stream_thinking_then_idle_during_send_message(self):
        status_stream = self.llm_service.stream_llm_status()

        thinking = asyncio.ensure_future(status_stream.__anext__())

        await asyncio.sleep(0)  # Let the status stream yield IDLE.

        await self.llm_service.send_message("Test message", self.test_game_state)

        self.assertEqual(await thinking, LLMStatus.THINKING)

        self.assertEqual(await status_stream.__anext__(), LLMStatus.IDLE)

        await status_stream.aclose()

    async def test_should_emit_idle_status_when_agent_invocation_fails(self):
        # Even when the agent call blows up, the `finally` block must still emit
        # IDLE so the UI never gets stuck showing "thinking".
        self.mock_agent.ainvoke = AsyncMock(side_effect=RuntimeError("agent down"))

        status_stream = self.llm_service.stream_llm_status()
        thinking = asyncio.ensure_future(status_stream.__anext__())
        await asyncio.sleep(0)

        with self.assertRaises(RuntimeError):
            await self.llm_service.send_message("Test message", self.test_game_state)

        self.assertEqual(await thinking, LLMStatus.THINKING)
        self.assertEqual(await status_stream.__anext__(), LLMStatus.IDLE)
        await status_stream.aclose()

    def test_get_tools_returns_perform_game_action_tool(self):
        tools = self.llm_service.get_tools()

        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, "perform_game_action")

    async def test_perform_game_action_tool_publishes_resolved_action_to_event_bus(
        self,
    ):
        self.event_bus.publish = AsyncMock()
        tool = self.llm_service.get_tools()[0]

        result = await tool.ainvoke({"action": "ToggleFlightAssist"})

        self.event_bus.publish.assert_called_once_with(EdAction.TOGGLE_FLIGHT_ASSIST)
        self.assertEqual(result, "Action performed: ToggleFlightAssist")

    def test_perform_game_action_tool_rejects_unknown_action_value(self):
        tool = self.llm_service.get_tools()[0]

        with self.assertRaises(ValidationError):
            tool.invoke({"action": "NotARealAction"})
