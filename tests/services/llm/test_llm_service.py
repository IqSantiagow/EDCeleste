import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartEndEvent,
    RetryPromptPart,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from edceleste.services.models.message_block import (
    AgentFullResponse,
    AgentText,
    SystemMessage,
    Thinking,
    ToolCall,
    ToolResult,
    UserMessage,
)
from edceleste.services.event_bus import EventBus
from edceleste.services.llm_service import (
    EVENT_REACTION_PROMPT,
    SYSTEM_PROMPT,
    VOICE_RESPONSE_RULES,
    LLMService,
)
from edceleste.services.models.event_reaction_event import EventReactionEvent
from edceleste.services.models.game_events import LoadedGameEvent
from edceleste.services.models.game_state_changed_event import GameStateChangedEvent
from edceleste.services.models.llm_status import LLMStatus
from edceleste.services.models.settings_model import (
    LLMModel,
    LLMProviderModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from edceleste.services.settings_service import SettingsService


def _make_settings(system_prompt: str = SYSTEM_PROMPT) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(volume=1.0),
        llm=LLMModel(system_prompt=system_prompt, user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


def _make_agent_stream_of(blocks: list):
    """Build a fake stream_agent_response that yields the given blocks."""

    async def stream_agent_response(prompt: str):
        for block in blocks:
            yield block

    return stream_agent_response


def _make_failing_agent_stream(error: Exception):
    """Build a fake stream_agent_response that blows up instead of yielding."""

    async def stream_agent_response(prompt: str):
        raise error
        yield  # pragma: no cover - only here to keep this an async generator

    return stream_agent_response


def _make_models_listing(model_ids: list[str]) -> Mock:
    """Mimic what the OpenRouter client returns from models.list()."""
    return Mock(data=[Mock(id=model_id) for model_id in model_ids])


def _make_loaded_game_event() -> LoadedGameEvent:
    return LoadedGameEvent(
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


class FakeTool:
    """Minimal ToolProtocol implementation, so no real game services are needed."""

    readable_name = "Perform Game Action"
    param_name = "action"
    name = "perform_game_action"

    async def execute(self, action: str) -> str:
        """Perform a game action"""
        return f"Performed game action: {action}"


class LLMServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # The agent is a real pydantic_ai Agent in production; patch the class so
        # no model is built and no network call is made.
        agent_patcher = patch("edceleste.services.llm_service.Agent")
        self.mock_agent_class = agent_patcher.start()
        self.addCleanup(agent_patcher.stop)

        # Building the provider and the model both need a reachable OpenRouter.
        provider_patcher = patch.object(LLMService, "determine_provider")
        self.mock_determine_provider = provider_patcher.start()
        self.addCleanup(provider_patcher.stop)

        model_patcher = patch.object(LLMService, "build_model")
        model_patcher.start()
        self.addCleanup(model_patcher.stop)

        # Every turn reads from this stream; the mapping of raw pydantic_ai events
        # onto message blocks is covered by TestLLMServiceEventMapping instead.
        stream_patcher = patch.object(LLMService, "stream_agent_response")
        self.mock_stream_agent_response = stream_patcher.start()
        self.addCleanup(stream_patcher.stop)
        self.mock_stream_agent_response.side_effect = _make_agent_stream_of(
            [AgentText(content="Test output 1")]
        )

        self.test_game_state = "Test game state"
        self.event_bus = EventBus()
        self.settings_handler = Mock(spec=SettingsService)
        self.settings_handler.get_settings.return_value = _make_settings()
        self.llm_service = LLMService(
            event_bus=self.event_bus,
            settings_service=self.settings_handler,
            tools=[],
        )
        # The agent is built in reload_service(), driven by the cold-start flow.
        self.llm_service.reload_service()
        # Game state is cached from the last GameStateChangedEvent seen on the bus.
        self.llm_service.game_state = self.test_game_state

        self.llm_stream = self.llm_service.consume_llm_queue()
        self.addAsyncCleanup(self.llm_stream.aclose)

    async def _collect_stream_items(self, item_count: int) -> list:
        collected_items = []

        for _ in range(item_count):
            collected_items.append(await self.llm_stream.__anext__())

        return collected_items

    async def test_should_stream_thinking_then_response_then_idle(self):
        self.llm_service.add_llm_request_to_queue("Test message")

        items = await self._collect_stream_items(3)

        self.assertEqual(
            items,
            [
                LLMStatus.THINKING,
                AgentText(content="Test output 1"),
                LLMStatus.IDLE,
            ],
        )

    async def test_should_add_user_message_and_agent_response_to_conversation(self):
        self.llm_service.add_llm_request_to_queue("Test message")

        await self._collect_stream_items(3)

        conversation = self.llm_service.conversation
        self.assertIn(UserMessage(content="Test message"), conversation)
        self.assertIn(
            AgentFullResponse(content="Test output 1", tool_calls=[], tool_results=[]),
            conversation,
        )

    async def test_should_pass_system_prompt_to_agent_and_game_state_in_prompt(self):
        self.llm_service.add_llm_request_to_queue("Test message")

        await self._collect_stream_items(3)

        self.assertEqual(
            self.mock_agent_class.call_args.kwargs["system_prompt"],
            f"{VOICE_RESPONSE_RULES}\n{SYSTEM_PROMPT}",
        )
        self.assertIn(
            self.test_game_state,
            self.mock_stream_agent_response.call_args.args[0],
        )

    async def test_should_publish_tts_event_for_every_agent_text(self):
        self.event_bus.publish = AsyncMock()
        self.mock_stream_agent_response.side_effect = _make_agent_stream_of(
            [AgentText(content="First"), AgentText(content="Second")]
        )
        self.llm_service.add_llm_request_to_queue("Test message")

        await self._collect_stream_items(4)

        published_texts = [
            call.args[0].text for call in self.event_bus.publish.await_args_list
        ]
        self.assertEqual(published_texts, ["First", "Second"])

    async def test_should_yield_agent_text_before_speaking_it(self):
        # Speaking blocks the turn, so COMMS has to get the text first - otherwise
        # the entry shows up only after Celeste stopped talking.
        speech_finished = False

        async def speak_slowly(event) -> None:
            nonlocal speech_finished
            await asyncio.sleep(0.05)
            speech_finished = True

        self.event_bus.publish = speak_slowly
        self.llm_service.add_llm_request_to_queue("Test message")

        items = await self._collect_stream_items(2)

        self.assertEqual(items[1], AgentText(content="Test output 1"))
        self.assertFalse(speech_finished)

    async def test_should_answer_with_system_message_when_game_state_not_set(self):
        # Before any GameStateChangedEvent has arrived the agent must not be
        # called at all - the turn short-circuits with a SystemMessage instead
        # of building a prompt around a missing game state.
        self.llm_service.game_state = None
        self.llm_service.add_llm_request_to_queue("Test message")

        items = await self._collect_stream_items(3)

        self.assertEqual(
            items,
            [
                LLMStatus.THINKING,
                SystemMessage(
                    content="Game state is not set. Cannot send message to LLM."
                ),
                LLMStatus.IDLE,
            ],
        )
        self.mock_stream_agent_response.assert_not_called()
        self.assertEqual(self.llm_service.conversation, [])

    async def test_should_report_failed_turn_and_keep_serving_next_message(self):
        # A single broken turn cannot kill the stream - it is the only source of
        # data for COMMS.
        self.mock_stream_agent_response.side_effect = _make_failing_agent_stream(
            RuntimeError("agent down")
        )
        self.llm_service.add_llm_request_to_queue("Failing message")

        failed_turn_items = await self._collect_stream_items(3)

        self.assertEqual(failed_turn_items[0], LLMStatus.THINKING)
        self.assertEqual(
            failed_turn_items[1],
            SystemMessage(content="LLM turn failed: agent down"),
        )
        self.assertEqual(failed_turn_items[2], LLMStatus.IDLE)

        self.mock_stream_agent_response.side_effect = _make_agent_stream_of(
            [AgentText(content="Test output 2")]
        )
        self.llm_service.add_llm_request_to_queue("Next message")

        next_turn_items = await self._collect_stream_items(3)

        self.assertEqual(
            next_turn_items,
            [
                LLMStatus.THINKING,
                AgentText(content="Test output 2"),
                LLMStatus.IDLE,
            ],
        )

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

    async def test_process_event_reaction_queues_event_description_prompt(self):
        loaded_game_event = _make_loaded_game_event()

        await self.llm_service.process_event_reaction(
            EventReactionEvent(event=loaded_game_event)
        )
        await self._collect_stream_items(3)

        self.assertIn(
            UserMessage(
                content=EVENT_REACTION_PROMPT.format(
                    event_description=loaded_game_event.model_dump_json()
                )
            ),
            self.llm_service.conversation,
        )

    # --- settings ---

    async def test_validate_settings_reports_no_issues_for_a_known_model(self):
        settings = _make_settings()
        settings.llm.provider.model = "anthropic/claude-haiku-4.5"
        self.mock_determine_provider.return_value.client.models.list = AsyncMock(
            return_value=_make_models_listing(["anthropic/claude-haiku-4.5"])
        )

        issue = await self.llm_service.validate_settings(settings)

        self.assertIsNone(issue)

    async def test_validate_settings_rejects_a_model_openrouter_does_not_serve(self):
        settings = _make_settings()
        settings.llm.provider.model = "not/a-real-model"
        self.mock_determine_provider.return_value.client.models.list = AsyncMock(
            return_value=_make_models_listing(["anthropic/claude-haiku-4.5"])
        )

        issue = await self.llm_service.validate_settings(settings)

        assert issue is not None
        self.assertEqual(issue.field, "llm.provider.model")

    async def test_validate_settings_rejects_an_unsupported_provider_type(self):
        settings = _make_settings()
        settings.llm.provider = Mock(type="lm_studio")

        issue = await self.llm_service.validate_settings(settings)

        assert issue is not None
        self.assertEqual(issue.field, "llm.provider.type")

    async def test_validate_settings_accepts_any_model_when_no_list_is_published(
        self,
    ):
        # ollama, vllm and azure publish nothing to check the name against, so
        # whatever the pilot typed has to pass.
        settings = _make_settings()
        settings.llm.provider.model = "some-local-model"
        self.mock_determine_provider.return_value = Mock(spec=[])

        issue = await self.llm_service.validate_settings(settings)

        self.assertIsNone(issue)

    async def test_validate_settings_reports_a_provider_that_cannot_be_built(self):
        # Picking groq without its package installed must come back as a
        # validation issue instead of crashing the save.
        settings = _make_settings()
        self.mock_determine_provider.side_effect = ImportError(
            "Please install the `groq` package"
        )

        issue = await self.llm_service.validate_settings(settings)

        assert issue is not None
        self.assertEqual(issue.field, "llm.provider.type")
        self.assertIn("groq", issue.message)

    async def test_get_models_returns_nothing_when_the_provider_has_no_listing(self):
        self.mock_determine_provider.return_value = Mock(spec=[])

        self.assertEqual(await self.llm_service.get_models(), [])

    async def test_get_models_returns_the_ids_the_provider_serves(self):
        self.mock_determine_provider.return_value.client.models.list = AsyncMock(
            return_value=_make_models_listing(["openai/gpt-4o", "google/gemini-pro"])
        )

        result = await self.llm_service.get_models()

        self.assertEqual(result, ["openai/gpt-4o", "google/gemini-pro"])

    # --- cold_start ---

    async def test_cold_start_yields_pending_status_first(self):
        # ColdStartStatus is mutated in place and re-yielded on completion, so
        # the pending status must be inspected right after this first yield -
        # collecting every yield into a list first would show the mutated,
        # already-completed object instead.
        first_status = await self.llm_service.cold_start().__anext__()

        self.assertEqual(first_status.service, "llm")
        self.assertFalse(first_status.is_critical)
        self.assertFalse(first_status.completed)
        self.assertIsNone(first_status.message)

    async def test_cold_start_yields_completed_status_when_health_check_succeeds(self):
        statuses = [status async for status in self.llm_service.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertIsNone(last_status.message)
        self.mock_stream_agent_response.assert_called_once()

    async def test_cold_start_yields_error_message_when_health_check_fails(self):
        self.mock_stream_agent_response.side_effect = _make_failing_agent_stream(
            RuntimeError("agent unreachable")
        )

        statuses = [status async for status in self.llm_service.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertEqual(last_status.message, "agent unreachable")

    def test_reload_service_rebuilds_agent_with_updated_system_prompt(self):
        new_settings = _make_settings(system_prompt="New system prompt")
        self.settings_handler.get_settings.return_value = new_settings

        self.llm_service.reload_service()

        self.assertEqual(
            self.mock_agent_class.call_args.kwargs["system_prompt"],
            f"{VOICE_RESPONSE_RULES}\nNew system prompt",
        )


class TestLLMServiceProvider(unittest.TestCase):
    """Nothing is patched here, so real pydantic_ai providers and models are built."""

    def setUp(self):
        self.llm_service = LLMService(
            event_bus=EventBus(),
            settings_service=Mock(spec=SettingsService),
            tools=[],
        )

    def test_should_build_the_provider_class_pydantic_ai_knows_for_that_name(self):
        provider = self.llm_service.determine_provider(
            LLMProviderModel(
                type="openrouter", model="anthropic/claude-haiku-4.5", api_key="key-123"
            )
        )

        self.assertIsInstance(provider, OpenRouterProvider)

    def test_should_build_any_other_supported_provider_the_same_way(self):
        # Nothing about openrouter is hard wired - every provider goes through
        # the same infer_provider_class call.
        provider = self.llm_service.determine_provider(
            LLMProviderModel(type="openai", model="gpt-4o", api_key="key-123")
        )

        self.assertIsInstance(provider, OpenAIProvider)

    def test_should_pass_a_custom_base_url_to_the_provider(self):
        provider = self.llm_service.determine_provider(
            LLMProviderModel(
                type="openai",
                model="qwen2.5",
                api_key="key-123",
                base_url="http://localhost:1234/v1",
            )
        )

        self.assertEqual(str(provider.base_url), "http://localhost:1234/v1/")

    def test_should_reject_a_provider_type_pydantic_ai_does_not_serve(self):
        with self.assertRaises(ValueError):
            self.llm_service.determine_provider(
                LLMProviderModel(type="lm_studio", model="llama-3", api_key="k")
            )

    def test_should_build_the_model_belonging_to_the_chosen_provider(self):
        settings = _make_settings()
        settings.llm.provider = LLMProviderModel(
            type="openrouter", model="anthropic/claude-haiku-4.5", api_key="key-123"
        )

        self.assertIsInstance(self.llm_service.build_model(settings), OpenRouterModel)

    def test_should_build_a_different_model_class_for_a_different_provider(self):
        settings = _make_settings()
        settings.llm.provider = LLMProviderModel(
            type="anthropic", model="claude-haiku-4-5-20251001", api_key="key-123"
        )

        self.assertIsInstance(self.llm_service.build_model(settings), AnthropicModel)


class TestLLMServiceEventMapping(unittest.TestCase):
    """pydantic_ai events carry more than the UI shows - only these map over."""

    def setUp(self):
        self.tool = FakeTool()
        self.llm_service = LLMService(
            event_bus=EventBus(),
            settings_service=Mock(spec=SettingsService),
            tools=[self.tool],
        )

    def test_should_map_a_finished_text_part_to_agent_text(self):
        event = PartEndEvent(index=0, part=TextPart(content="Hello Commander"))

        self.assertEqual(
            self.llm_service.to_message_block(event),
            AgentText(content="Hello Commander"),
        )

    def test_should_map_a_finished_thinking_part_to_thinking(self):
        event = PartEndEvent(index=0, part=ThinkingPart(content="weighing options"))

        self.assertEqual(
            self.llm_service.to_message_block(event),
            Thinking(content="weighing options"),
        )

    def test_should_ignore_text_deltas_so_speech_is_not_cut_into_pieces(self):
        event = PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="Hel"))

        self.assertIsNone(self.llm_service.to_message_block(event))

    def test_should_map_a_tool_call_to_the_readable_name_of_a_known_tool(self):
        event = FunctionToolCallEvent(
            part=ToolCallPart(
                tool_name="perform_game_action",
                args={"action": "ToggleFlightAssist"},
                tool_call_id="call-1",
            )
        )

        self.assertEqual(
            self.llm_service.to_message_block(event),
            ToolCall(
                tool_name="perform_game_action",
                input={"action": "ToggleFlightAssist"},
                tool_readable_name="Perform Game Action",
                param_name="action",
            ),
        )

    def test_should_fall_back_to_the_raw_name_for_an_unknown_tool(self):
        event = FunctionToolCallEvent(
            part=ToolCallPart(tool_name="mystery_tool", args={}, tool_call_id="call-1")
        )

        self.assertEqual(
            self.llm_service.to_message_block(event),
            ToolCall(
                tool_name="mystery_tool",
                input={},
                tool_readable_name="mystery_tool",
                param_name=None,
            ),
        )

    def test_should_read_the_error_flag_a_tool_put_in_its_metadata(self):
        event = FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name="perform_game_action",
                content="Game actions are disabled by the user.",
                tool_call_id="call-1",
                metadata={"is_error": True},
            )
        )

        self.assertEqual(
            self.llm_service.to_message_block(event),
            ToolResult(content="Game actions are disabled by the user.", is_error=True),
        )

    def test_should_map_a_successful_tool_result_without_an_error_flag(self):
        event = FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name="perform_game_action",
                content="Performed game action: Supercruise",
                tool_call_id="call-1",
                metadata={"is_error": False},
            )
        )

        self.assertEqual(
            self.llm_service.to_message_block(event),
            ToolResult(content="Performed game action: Supercruise", is_error=False),
        )

    def test_should_treat_a_retry_prompt_as_a_failed_tool_result(self):
        # A retry prompt means the model called the tool wrong, so the tool never
        # ran - the pilot still has to see that the action did not happen.
        event = FunctionToolResultEvent(
            part=RetryPromptPart(
                content="action is not a valid EdAction",
                tool_name="perform_game_action",
                tool_call_id="call-1",
            )
        )

        block = self.llm_service.to_message_block(event)

        assert isinstance(block, ToolResult)
        self.assertTrue(block.is_error)
        self.assertIn("not a valid EdAction", block.content)


class TestLLMServiceStreamsFromAgent(unittest.IsolatedAsyncioTestCase):
    """Drives a real Agent with a stubbed model, so the event loop is exercised."""

    async def test_should_stream_tool_call_result_and_text_of_a_real_agent_run(self):
        llm_service = LLMService(
            event_bus=EventBus(),
            settings_service=Mock(spec=SettingsService),
            tools=[FakeTool()],
        )
        with (
            patch.object(LLMService, "determine_provider"),
            patch.object(LLMService, "build_model", return_value=TestModel()),
        ):
            llm_service.reload_service()

        blocks = [
            block async for block in llm_service.stream_agent_response("do something")
        ]

        tool_calls = [block for block in blocks if isinstance(block, ToolCall)]
        tool_results = [block for block in blocks if isinstance(block, ToolResult)]

        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].tool_readable_name, "Perform Game Action")
        self.assertEqual(len(tool_results), 1)
        self.assertFalse(tool_results[0].is_error)
        self.assertTrue(any(isinstance(block, AgentText) for block in blocks))


if __name__ == "__main__":
    unittest.main()
