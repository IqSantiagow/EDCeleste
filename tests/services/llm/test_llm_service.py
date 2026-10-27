import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from pydantic_ai import ModelHTTPError, models
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
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
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from edceleste.services.models.message_block import (
    AgentText,
    SystemMessage,
    Thinking,
    ToolCall,
    ToolResult,
)
from edceleste.services.event_bus import EventBus
from edceleste.services.llm_service import (
    EVENT_REACTION_PROMPT,
    HISTORY_WINDOW_TURNS,
    SYSTEM_PROMPT,
    VOICE_RESPONSE_RULES,
    LLMService,
)
from edceleste.services.models.event_reaction_event import EventReactionEvent
from edceleste.services.models.game_events import LoadedGameEvent
from edceleste.services.models.game_state_changed_event import GameStateChangedEvent
from edceleste.services.models.llm_status import LLMStatus
from edceleste.services.models.service_status import ServiceState, ServiceStatus
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

    async def stream_agent_response(message: str):
        for block in blocks:
            yield block

    return stream_agent_response


def _make_failing_agent_stream(error: Exception):
    """Build a fake stream_agent_response that blows up instead of yielding."""

    async def stream_agent_response(message: str):
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


async def _latest_status(service: LLMService) -> ServiceStatus:
    """The status a new listener of stream_status() gets at once."""
    stream = service.stream_status()
    try:
        return await asyncio.wait_for(stream.__anext__(), timeout=1)
    finally:
        await stream.aclose()


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
        # The connection test awaits agent.run(), a plain Mock is not awaitable.
        self.mock_agent_class.return_value.run = AsyncMock()

        # Building the provider and the model both need a reachable OpenRouter.
        provider_patcher = patch.object(LLMService, "_LLMService__build_provider")
        self.mock_build_provider = provider_patcher.start()
        self.addCleanup(provider_patcher.stop)

        model_patcher = patch.object(LLMService, "_LLMService__build_model")
        model_patcher.start()
        self.addCleanup(model_patcher.stop)

        # Every turn reads from this stream; the mapping of raw pydantic_ai events
        # onto message blocks is covered by TestLLMServiceEventMapping instead.
        stream_patcher = patch.object(LLMService, "_LLMService__stream_agent_response")
        self.mock_stream_agent_response = stream_patcher.start()
        self.addCleanup(stream_patcher.stop)
        self.mock_stream_agent_response.side_effect = _make_agent_stream_of(
            [AgentText(content="Test output 1")]
        )

        self.test_game_state = "Test game state"
        self.event_bus = EventBus()
        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.return_value = _make_settings()
        self.llm_service = LLMService(
            event_bus=self.event_bus,
            settings_service=self.settings_service,
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

    async def test_should_send_only_the_message_to_the_agent(self):
        self.llm_service.add_llm_request_to_queue("Test message")

        await self._collect_stream_items(3)

        self.mock_stream_agent_response.assert_called_once_with("Test message")

    async def test_should_pass_system_prompt_and_game_state_to_agent_as_instructions(
        self,
    ):
        instructions = self.mock_agent_class.call_args.kwargs["instructions"]

        self.assertEqual(instructions[0], f"{VOICE_RESPONSE_RULES}\n{SYSTEM_PROMPT}")
        self.assertEqual(instructions[1](), "Current game state is:\nTest game state")

    async def test_should_follow_the_newest_game_state_in_the_instructions(self):
        await self.llm_service.remember_latest_game_state(
            GameStateChangedEvent(game_state="In supercruise")
        )

        instructions = self.mock_agent_class.call_args.kwargs["instructions"]

        self.assertEqual(instructions[1](), "Current game state is:\nIn supercruise")

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
        self.assertEqual(self.llm_service.history_turns, [])

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

    async def test_remember_latest_game_state_stores_the_game_state_text(self):
        await self.llm_service.remember_latest_game_state(
            GameStateChangedEvent(game_state="Docked at Jameson Memorial")
        )

        self.assertEqual(self.llm_service.game_state, "Docked at Jameson Memorial")

    async def test_game_state_changed_event_on_bus_updates_llm_service_game_state(
        self,
    ):
        # Confirms the subscription wired up in __init__: LLMService should
        # pick up a GameStateChangedEvent published by anyone on the bus, not
        # just via a direct call to remember_latest_game_state.
        await self.event_bus.publish(GameStateChangedEvent(game_state="In supercruise"))

        self.assertEqual(self.llm_service.game_state, "In supercruise")

    async def test_queue_reply_to_journal_event_puts_event_description_prompt(self):
        loaded_game_event = _make_loaded_game_event()

        await self.llm_service.queue_reply_to_journal_event(
            EventReactionEvent(event=loaded_game_event)
        )
        await self._collect_stream_items(3)

        self.mock_stream_agent_response.assert_called_once_with(
            EVENT_REACTION_PROMPT.format(
                event_description=loaded_game_event.model_dump_json()
            )
        )

    # --- settings ---

    async def test_validate_settings_reports_no_issues_for_a_known_model(self):
        settings = _make_settings()
        settings.llm.provider.model = "anthropic/claude-haiku-4.5"
        self.mock_build_provider.return_value.client.models.list = AsyncMock(
            return_value=_make_models_listing(["anthropic/claude-haiku-4.5"])
        )

        issue = await self.llm_service.validate_settings(settings)

        self.assertIsNone(issue)

    async def test_validate_settings_rejects_a_model_openrouter_does_not_serve(self):
        settings = _make_settings()
        settings.llm.provider.model = "not/a-real-model"
        self.mock_build_provider.return_value.client.models.list = AsyncMock(
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
        self.mock_build_provider.return_value = Mock(spec=[])

        issue = await self.llm_service.validate_settings(settings)

        self.assertIsNone(issue)

    async def test_validate_settings_reports_a_provider_that_cannot_be_built(self):
        # Picking groq without its package installed must come back as a
        # validation issue instead of crashing the save.
        settings = _make_settings()
        self.mock_build_provider.side_effect = ImportError(
            "Please install the `groq` package"
        )

        issue = await self.llm_service.validate_settings(settings)

        assert issue is not None
        self.assertEqual(issue.field, "llm.provider.type")
        self.assertIn("groq", issue.message)

    async def test_fetch_model_names_is_empty_when_the_provider_has_no_listing(
        self,
    ):
        self.mock_build_provider.return_value = Mock(spec=[])

        self.assertEqual(await self.llm_service.fetch_available_model_names(), [])

    async def test_fetch_available_model_names_returns_the_ids_the_provider_serves(
        self,
    ):
        self.mock_build_provider.return_value.client.models.list = AsyncMock(
            return_value=_make_models_listing(["openai/gpt-4o", "google/gemini-pro"])
        )

        result = await self.llm_service.fetch_available_model_names()

        self.assertEqual(result, ["openai/gpt-4o", "google/gemini-pro"])

    # --- status for the app header ---

    async def test_status_is_off_before_anything_was_checked(self):
        status = await _latest_status(self.llm_service)

        self.assertEqual(status, ServiceStatus(ServiceState.OFF, "Not checked yet"))

    async def test_status_is_ok_after_a_successful_request(self):
        self.llm_service.add_llm_request_to_queue("Test message")
        await self._collect_stream_items(3)

        status = await _latest_status(self.llm_service)

        self.assertEqual(
            status, ServiceStatus(ServiceState.OK, "The last request succeeded")
        )

    async def test_status_is_error_with_the_error_text_after_a_failed_request(self):
        self.mock_stream_agent_response.side_effect = _make_failing_agent_stream(
            RuntimeError("agent down")
        )
        self.llm_service.add_llm_request_to_queue("Failing message")
        await self._collect_stream_items(3)

        status = await _latest_status(self.llm_service)

        self.assertEqual(
            status,
            ServiceStatus(ServiceState.ERROR, "The last request failed: agent down"),
        )

    async def test_status_is_not_changed_by_a_reply_without_llm(self):
        self.llm_service.add_reply_without_llm_to_queue(
            "deploy landing gear", "Done: Landing gear toggle"
        )
        await self._collect_stream_items(1)

        status = await _latest_status(self.llm_service)

        self.assertEqual(status, ServiceStatus(ServiceState.OFF, "Not checked yet"))

    async def test_cold_start_sets_ok_status_when_the_llm_answers(self):
        [status async for status in self.llm_service.cold_start()]

        status = await _latest_status(self.llm_service)

        self.assertEqual(status, ServiceStatus(ServiceState.OK, "The LLM answered"))

    async def test_cold_start_sets_error_status_with_the_message_when_the_test_fails(
        self,
    ):
        self.mock_agent_class.return_value.run.side_effect = RuntimeError(
            "agent unreachable"
        )

        [status async for status in self.llm_service.cold_start()]

        status = await _latest_status(self.llm_service)
        self.assertEqual(status, ServiceStatus(ServiceState.ERROR, "agent unreachable"))

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
        self.mock_agent_class.return_value.run.assert_awaited_once()

    async def test_cold_start_yields_error_message_when_health_check_fails(self):
        self.mock_agent_class.return_value.run.side_effect = RuntimeError(
            "agent unreachable"
        )

        statuses = [status async for status in self.llm_service.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertEqual(last_status.message, "agent unreachable")

    async def test_find_connection_error_redacts_api_keys_from_provider_errors(self):
        provider = _make_settings().llm.provider
        provider.api_key = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456"
        self.mock_agent_class.return_value.run.side_effect = RuntimeError(
            f"request failed for {provider.api_key}"
        )

        error_message = await self.llm_service.find_connection_error(provider)

        self.assertEqual(
            error_message,
            "request failed for [REDACTED API KEY]",
        )

    async def test_find_connection_error_keeps_error_message_when_api_key_is_empty(
        self,
    ):
        self.mock_agent_class.return_value.run.side_effect = RuntimeError(
            "Connection refused by the provider"
        )

        error_message = await self.llm_service.find_connection_error(
            _make_settings().llm.provider
        )

        self.assertEqual(error_message, "Connection refused by the provider")

    async def test_find_connection_error_returns_status_code_and_provider_reason(self):
        self.mock_agent_class.return_value.run.side_effect = ModelHTTPError(
            401, "some-model", body={"error": {"message": "Invalid API key"}}
        )

        error_message = await self.llm_service.find_connection_error(
            _make_settings().llm.provider
        )

        self.assertEqual(error_message, "HTTP 401: Invalid API key")

    async def test_find_connection_error_says_no_answer_when_the_provider_times_out(
        self,
    ):
        self.mock_agent_class.return_value.run.side_effect = TimeoutError()

        error_message = await self.llm_service.find_connection_error(
            _make_settings().llm.provider
        )

        self.assertEqual(error_message, "No answer within 15 s")

    async def test_find_connection_error_cuts_long_errors_to_200_characters(self):
        self.mock_agent_class.return_value.run.side_effect = RuntimeError("x" * 500)

        error_message = await self.llm_service.find_connection_error(
            _make_settings().llm.provider
        )

        self.assertEqual(error_message, "x" * 200)

    def test_reload_service_rebuilds_agent_with_updated_system_prompt(self):
        new_settings = _make_settings(system_prompt="New system prompt")
        self.settings_service.get_settings.return_value = new_settings

        self.llm_service.reload_service()

        self.assertEqual(
            self.mock_agent_class.call_args.kwargs["instructions"][0],
            f"{VOICE_RESPONSE_RULES}\nNew system prompt",
        )

    # A reply without the LLM answers a command Instinct handled: no LLM, no speech.

    async def test_should_yield_a_reply_without_llm_as_one_agent_text_without_statuses(
        self,
    ):
        self.llm_service.add_reply_without_llm_to_queue(
            "deploy landing gear", "Done: Landing gear toggle"
        )
        # The next queued message proves nothing else was yielded in between
        self.llm_service.add_llm_request_to_queue("Test message")

        items = await self._collect_stream_items(4)

        self.assertEqual(
            items,
            [
                AgentText(content="Done: Landing gear toggle"),
                LLMStatus.THINKING,
                AgentText(content="Test output 1"),
                LLMStatus.IDLE,
            ],
        )

    async def test_should_not_call_the_llm_for_a_reply_without_llm(self):
        self.llm_service.add_reply_without_llm_to_queue(
            "deploy landing gear", "Done: Landing gear toggle"
        )

        await self._collect_stream_items(1)

        self.mock_stream_agent_response.assert_not_called()

    async def test_should_write_a_reply_without_llm_to_the_conversation_history(self):
        self.llm_service.add_reply_without_llm_to_queue(
            "deploy landing gear", "Done: Landing gear toggle"
        )

        await self._collect_stream_items(1)

        [[pilot_request, celeste_reply]] = self.llm_service.history_turns
        self.assertIsInstance(pilot_request, ModelRequest)
        self.assertEqual(pilot_request.parts[0].content, "deploy landing gear")
        self.assertIsInstance(celeste_reply, ModelResponse)
        self.assertEqual(celeste_reply.parts[0].content, "Done: Landing gear toggle")

    async def test_should_not_speak_a_reply_without_llm(self):
        self.event_bus.publish = AsyncMock()
        self.llm_service.add_reply_without_llm_to_queue(
            "deploy landing gear", "Done: Landing gear toggle"
        )
        # Resuming the stream with a normal turn lets any speech after the
        # reply without the LLM happen before we look
        self.llm_service.add_llm_request_to_queue("Test message")

        await self._collect_stream_items(4)

        published_texts = [
            call.args[0].text for call in self.event_bus.publish.await_args_list
        ]
        self.assertEqual(published_texts, ["Test output 1"])

    async def test_should_keep_replies_without_llm_in_the_order_they_were_queued(self):
        self.llm_service.add_reply_without_llm_to_queue("first command", "Done: First")
        self.llm_service.add_reply_without_llm_to_queue(
            "second command", "Done: Second"
        )

        items = await self._collect_stream_items(2)

        self.assertEqual(
            items, [AgentText(content="Done: First"), AgentText(content="Done: Second")]
        )

    async def test_should_keep_the_window_when_a_reply_without_llm_is_added(self):
        for number in range(HISTORY_WINDOW_TURNS + 3):
            self.llm_service.add_reply_without_llm_to_queue(
                f"command {number}", f"Done: {number}"
            )

        await self._collect_stream_items(HISTORY_WINDOW_TURNS + 3)

        first_kept = self.llm_service.history_turns[0][0]
        self.assertEqual(len(self.llm_service.history_turns), HISTORY_WINDOW_TURNS)
        self.assertEqual(first_kept.parts[0].content, "command 3")


class TestLLMServiceProvider(unittest.TestCase):
    """Nothing is patched here, so real pydantic_ai providers and models are built."""

    def setUp(self):
        self.llm_service = LLMService(
            event_bus=EventBus(),
            settings_service=Mock(spec=SettingsService),
            tools=[],
        )

    def test_should_build_the_provider_class_pydantic_ai_knows_for_that_name(self):
        provider = self.llm_service._LLMService__build_provider(
            LLMProviderModel(
                type="openrouter", model="anthropic/claude-haiku-4.5", api_key="key-123"
            )
        )

        self.assertIsInstance(provider, OpenRouterProvider)

    def test_should_build_any_other_supported_provider_the_same_way(self):
        # Nothing about openrouter is hard wired - every provider goes through
        # the same infer_provider_class call.
        provider = self.llm_service._LLMService__build_provider(
            LLMProviderModel(type="openai", model="gpt-4o", api_key="key-123")
        )

        self.assertIsInstance(provider, OpenAIProvider)

    def test_should_pass_a_custom_base_url_to_the_provider(self):
        provider = self.llm_service._LLMService__build_provider(
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
            self.llm_service._LLMService__build_provider(
                LLMProviderModel(type="lm_studio", model="llama-3", api_key="k")
            )

    def test_should_build_the_model_belonging_to_the_chosen_provider(self):
        provider = LLMProviderModel(
            type="openrouter", model="anthropic/claude-haiku-4.5", api_key="key-123"
        )

        self.assertIsInstance(
            self.llm_service._LLMService__build_model(provider), OpenRouterModel
        )

    def test_should_build_a_different_model_class_for_a_different_provider(self):
        provider = LLMProviderModel(
            type="anthropic", model="claude-haiku-4-5-20251001", api_key="key-123"
        )

        self.assertIsInstance(
            self.llm_service._LLMService__build_model(provider), AnthropicModel
        )

    def test_find_connection_error_should_build_the_model_and_reach_the_request(self):
        # Blocked requests fail only at the request itself, so this error proves
        # the model got built from the provider
        provider = LLMProviderModel(
            type="openrouter", model="anthropic/claude-haiku-4.5", api_key="key-123"
        )

        with patch.object(models, "ALLOW_MODEL_REQUESTS", False):
            error_message = asyncio.run(
                self.llm_service.find_connection_error(provider)
            )

        self.assertEqual(
            error_message,
            "Model requests are not allowed, since ALLOW_MODEL_REQUESTS is False",
        )


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
            self.llm_service._LLMService__to_message_block(event),
            AgentText(content="Hello Commander"),
        )

    def test_should_map_a_finished_thinking_part_to_thinking(self):
        event = PartEndEvent(index=0, part=ThinkingPart(content="weighing options"))

        self.assertEqual(
            self.llm_service._LLMService__to_message_block(event),
            Thinking(content="weighing options"),
        )

    def test_should_ignore_text_deltas_so_speech_is_not_cut_into_pieces(self):
        event = PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="Hel"))

        self.assertIsNone(self.llm_service._LLMService__to_message_block(event))

    def test_should_map_a_tool_call_to_the_readable_name_of_a_known_tool(self):
        event = FunctionToolCallEvent(
            part=ToolCallPart(
                tool_name="perform_game_action",
                args={"action": "ToggleFlightAssist"},
                tool_call_id="call-1",
            )
        )

        self.assertEqual(
            self.llm_service._LLMService__to_message_block(event),
            ToolCall(
                tool_name="perform_game_action",
                input={"action": "ToggleFlightAssist"},
                tool_readable_name="Perform Game Action",
                param_name="action",
            ),
        )

    def test_should_write_a_tool_call_and_its_result_to_the_log_file(self):
        call_event = FunctionToolCallEvent(
            part=ToolCallPart(
                tool_name="perform_game_action",
                args={"action": "LandingGearToggle"},
                tool_call_id="call-1",
            )
        )
        result_event = FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name="perform_game_action",
                content="Performed LandingGearToggle",
                tool_call_id="call-1",
            )
        )

        with self.assertLogs("edceleste.services.llm_service", "INFO") as logs:
            self.llm_service._LLMService__to_message_block(call_event)
            self.llm_service._LLMService__to_message_block(result_event)

        self.assertIn("LandingGearToggle", logs.output[0])
        self.assertIn("Performed LandingGearToggle", logs.output[1])

    def test_should_fall_back_to_the_raw_name_for_an_unknown_tool(self):
        event = FunctionToolCallEvent(
            part=ToolCallPart(tool_name="mystery_tool", args={}, tool_call_id="call-1")
        )

        self.assertEqual(
            self.llm_service._LLMService__to_message_block(event),
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
            self.llm_service._LLMService__to_message_block(event),
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
            self.llm_service._LLMService__to_message_block(event),
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

        block = self.llm_service._LLMService__to_message_block(event)

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
            patch.object(LLMService, "_LLMService__build_provider"),
            patch.object(
                LLMService, "_LLMService__build_model", return_value=TestModel()
            ),
        ):
            llm_service.reload_service()

        blocks = [
            block
            async for block in llm_service._LLMService__stream_agent_response(
                "do something"
            )
        ]

        tool_calls = [block for block in blocks if isinstance(block, ToolCall)]
        tool_results = [block for block in blocks if isinstance(block, ToolResult)]

        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].tool_readable_name, "Perform Game Action")
        self.assertEqual(len(tool_results), 1)
        self.assertFalse(tool_results[0].is_error)
        self.assertTrue(any(isinstance(block, AgentText) for block in blocks))


class TestLLMServiceHistory(unittest.IsolatedAsyncioTestCase):
    """Drives a real Agent with a function model that records what it receives."""

    def setUp(self):
        self.llm_service = LLMService(
            event_bus=EventBus(),
            settings_service=Mock(spec=SettingsService),
            tools=[],
        )
        self.llm_service.game_state = "Docked at Jameson Memorial"
        self.requests_seen_by_model: list[tuple[list, str | None]] = []

    def _use_model_that_answers(self, answer: str) -> None:
        async def answer_and_record(messages: list, info: AgentInfo):
            self.requests_seen_by_model.append((messages, info.instructions))
            yield answer

        with (
            patch.object(LLMService, "_LLMService__build_provider"),
            patch.object(
                LLMService,
                "_LLMService__build_model",
                return_value=FunctionModel(stream_function=answer_and_record),
            ),
        ):
            self.llm_service.reload_service()

    async def _ask(self, message: str) -> None:
        async for _ in self.llm_service._LLMService__stream_agent_response(message):
            pass

    async def test_should_save_the_message_and_the_reply_in_the_history(self):
        self._use_model_that_answers("Hello Commander")

        await self._ask("Hello")

        [[pilot_request, celeste_reply]] = self.llm_service.history_turns
        self.assertEqual(pilot_request.parts[0].content, "Hello")
        self.assertEqual(celeste_reply.parts[0].content, "Hello Commander")

    async def test_should_send_the_earlier_turns_with_the_next_message(self):
        self._use_model_that_answers("Hello Commander")
        await self._ask("Hello")

        await self._ask("Where are we?")

        messages_of_second_run, _ = self.requests_seen_by_model[1]
        self.assertEqual(len(messages_of_second_run), 3)
        self.assertEqual(messages_of_second_run[0].parts[0].content, "Hello")
        self.assertEqual(messages_of_second_run[2].parts[0].content, "Where are we?")

    async def test_should_give_the_newest_game_state_to_every_run(self):
        self._use_model_that_answers("OK")
        await self._ask("Hello")
        self.llm_service.game_state = "In supercruise"

        await self._ask("Where are we?")

        self.assertIn("Docked at Jameson Memorial", self.requests_seen_by_model[0][1])
        self.assertIn("In supercruise", self.requests_seen_by_model[1][1])
        self.assertNotIn(
            "Docked at Jameson Memorial", self.requests_seen_by_model[1][1]
        )

    async def test_should_keep_only_the_newest_turns_after_many_runs(self):
        self._use_model_that_answers("OK")

        for number in range(HISTORY_WINDOW_TURNS + 5):
            await self._ask(f"message {number}")

        first_kept_request = self.llm_service.history_turns[0][0]
        self.assertEqual(len(self.llm_service.history_turns), HISTORY_WINDOW_TURNS)
        self.assertEqual(first_kept_request.parts[0].content, "message 5")

    async def test_should_not_save_anything_when_the_run_fails(self):
        async def break_down(messages: list, info: AgentInfo):
            raise RuntimeError("provider down")
            yield  # pragma: no cover - only here to keep this an async generator

        with (
            patch.object(LLMService, "_LLMService__build_provider"),
            patch.object(
                LLMService,
                "_LLMService__build_model",
                return_value=FunctionModel(stream_function=break_down),
            ),
        ):
            self.llm_service.reload_service()

        with self.assertRaises(RuntimeError):
            await self._ask("Hello")

        self.assertEqual(self.llm_service.history_turns, [])

    async def test_should_keep_tool_calls_and_their_results_in_the_history(self):
        llm_service = LLMService(
            event_bus=EventBus(),
            settings_service=Mock(spec=SettingsService),
            tools=[FakeTool()],
        )
        with (
            patch.object(LLMService, "_LLMService__build_provider"),
            patch.object(
                LLMService, "_LLMService__build_model", return_value=TestModel()
            ),
        ):
            llm_service.reload_service()
        llm_service.game_state = "Docked at Jameson Memorial"

        blocks = [
            block
            async for block in llm_service._LLMService__stream_agent_response(
                "deploy gear"
            )
        ]

        self.assertTrue(any(isinstance(block, ToolCall) for block in blocks))
        [turn_messages] = llm_service.history_turns
        kept_parts = [part for message in turn_messages for part in message.parts]
        self.assertTrue(any(isinstance(part, ToolCallPart) for part in kept_parts))
        self.assertTrue(any(isinstance(part, ToolReturnPart) for part in kept_parts))


if __name__ == "__main__":
    unittest.main()
