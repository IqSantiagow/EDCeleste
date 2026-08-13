import asyncio
from datetime import datetime
import unittest
from unittest.mock import AsyncMock, Mock, patch

import anthropic
import httpx
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from services.event_bus import EventBus
from services.llm_service import EVENT_REACTION_PROMPT, SYSTEM_PROMPT, LLMService
from services.models.event_reaction_event import EventReactionEvent
from services.models.game_events import LoadedGameEvent
from services.models.game_state_changed_event import GameStateChangedEvent
from services.models.keybinds_model import EdAction
from services.models.llm_response import LLMResponseSource, LLMStatus
from services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsModel,
    TTSModel,
)
from services.settings_service import SettingsService


def _make_settings(api_key: str) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(api_key=api_key, system_prompt=SYSTEM_PROMPT, user_prompt=""),
    )


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
                {"structured_response": {"message": "Test output 1"}},
                {"structured_response": {"message": "Test output 2"}},
            ]
        )

        self.test_game_state = "Test game state"
        self.event_bus = EventBus()
        self.settings_handler = Mock(spec=SettingsService)
        self.settings_handler.get_settings.return_value = _make_settings(
            api_key="sk-ant-test"
        )
        self.llm_service = LLMService(
            event_bus=self.event_bus,
            settings_handler=self.settings_handler,
        )
        # Game state is no longer passed into send_message(); it's cached from
        # the last GameStateChangedEvent seen on the bus (see
        # process_game_state_change). Set it directly here so existing
        # send_message tests keep exercising the "state known" path.
        self.llm_service.game_state = self.test_game_state

    async def test_should_stream_the_received_message_to_subscribers(self):
        stream = self.llm_service.stream_responses()
        # Prime the subscriber: pulling once registers its queue before we send.
        # A late subscriber would miss the response (pub/sub, no replay).
        next_response = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await self.llm_service.send_message("Test message")

        response = await next_response
        self.assertEqual(response.message, "Test output 1")
        await stream.aclose()

    async def test_should_add_message_to_conv_history(self):
        message1 = "Test message 1"
        message2 = "Test message 2"

        await self.llm_service.send_message(message1)
        await self.llm_service.send_message(message2)

        conversation = self.llm_service.conversation
        self.assertIn(HumanMessage(content=message1), conversation)
        self.assertIn(HumanMessage(content=message2), conversation)
        self.assertIn(AIMessage(content="Test output 1"), conversation)
        self.assertIn(AIMessage(content="Test output 2"), conversation)

    async def test_should_pass_system_prompt_and_game_state_to_the_agent(self):
        await self.llm_service.send_message("Test message 1")

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

        await self.llm_service.send_message("Test message")

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
            await self.llm_service.send_message("Test message")

        self.assertEqual(await thinking, LLMStatus.THINKING)
        self.assertEqual(await status_stream.__anext__(), LLMStatus.IDLE)
        await status_stream.aclose()

    async def test_process_game_state_change_updates_cached_game_state(self):
        await self.llm_service.process_game_state_change(
            GameStateChangedEvent(game_state="Docked at Jameson Memorial")
        )

        self.assertEqual(self.llm_service.game_state, "Docked at Jameson Memorial")

    async def test_game_state_changed_event_on_bus_updates_llm_service_game_state(
        self,
    ):
        # Confirms the subscription wired up in __init__: LLMService should
        # pick up a GameStateChangedEvent published by anyone on the bus, not
        # just via a direct call to process_game_state_change.
        await self.event_bus.publish(GameStateChangedEvent(game_state="In supercruise"))

        self.assertEqual(self.llm_service.game_state, "In supercruise")

    async def test_send_message_responds_with_system_message_when_game_state_not_set(
        self,
    ):
        # Before any GameStateChangedEvent has arrived, send_message must not
        # call the agent at all - it should short-circuit with an LLMResponse
        # sourced as SYSTEM instead of building a prompt around a missing game
        # state.
        self.llm_service.game_state = None
        stream = self.llm_service.stream_responses()
        next_response = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0)

        await self.llm_service.send_message("Test message")

        response = await next_response
        self.assertEqual(response.source, LLMResponseSource.SYSTEM)
        self.assertEqual(
            response.message,
            "Game state is not set. Cannot send message to LLM.",
        )
        self.mock_agent.ainvoke.assert_not_called()
        # send_message returns before appending anything when game_state is
        # None, so the message never reaches conversation history - only a
        # real (agent-processed) turn does.
        self.assertNotIn(
            HumanMessage(content="Test message"), self.llm_service.conversation
        )
        self.assertNotIn(
            AIMessage(content="Test output 1"), self.llm_service.conversation
        )
        await stream.aclose()

    async def test_respond_with_system_message_pushes_to_all_subscribers(self):
        stream1 = self.llm_service.stream_responses()
        stream2 = self.llm_service.stream_responses()
        next1 = asyncio.ensure_future(stream1.__anext__())
        next2 = asyncio.ensure_future(stream2.__anext__())
        await asyncio.sleep(0)

        await self.llm_service.respond_with_system_message("custom system message")

        for pending in (next1, next2):
            response = await pending
            self.assertEqual(response.source, LLMResponseSource.SYSTEM)
            self.assertEqual(response.message, "custom system message")
        await stream1.aclose()
        await stream2.aclose()

    async def test_process_event_reaction_sends_event_description_to_llm(self):
        # Target behavior for the event-reactions feature: LLMService should
        # react to an EventReactionEvent by asking the agent to comment on it,
        # reusing the already-cached game state (send_message no longer takes
        # a game_state argument).
        loaded_game_event = LoadedGameEvent(
            event="LoadGame",
            timestamp=datetime.now(),
            Commander="TestCommander",
            FID="F123456",
            Horizons=True,
            Odyssey=False,
            Ship="Sidewinder",
            ShipID=1,
            ShipIdent="TS-001",
            ShipName="Test Ship",
            StartLanded=False,
            StartDead=False,
            GameMode="Solo",
            Group="",
            Credits=1000000,
            Loan=0,
            FuelLevel=1.0,
            FuelCapacity=4.0,
        )
        reaction_event = EventReactionEvent(event=loaded_game_event)
        self.llm_service.send_message = AsyncMock()

        await self.llm_service.process_event_reaction(reaction_event)

        self.llm_service.send_message.assert_called_once_with(
            message=EVENT_REACTION_PROMPT.format(
                event_description=loaded_game_event.model_dump_json()
            )
        )

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

    def test_validate_settings_reports_issue_when_api_key_missing(self):
        settings = _make_settings(api_key="")

        issue = self.llm_service.validate_settings(settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.field, "api_key")

    def test_validate_settings_returns_no_issues_when_api_key_present(self):
        settings = _make_settings(api_key="sk-ant-test")

        issue = self.llm_service.validate_settings(settings)

        self.assertIsNone(issue)

    def test_reload_service_rebuilds_agent_using_updated_system_prompt(self):
        new_settings = _make_settings(api_key="sk-ant-new")
        new_settings.llm.system_prompt = "New system prompt"
        self.settings_handler.get_settings.return_value = new_settings

        self.llm_service.reload_service()

        self.assertEqual(
            self.mock_create_agent.call_args.kwargs["system_prompt"],
            "New system prompt",
        )
