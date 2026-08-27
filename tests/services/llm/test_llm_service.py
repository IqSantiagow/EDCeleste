import asyncio
import unittest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from services.models.message_block import (
    AgentFullResponse,
    AgentText,
    SystemMessage,
    UserMessage,
)
from services.event_bus import EventBus
from services.llm_service import (
    EVENT_REACTION_PROMPT,
    SYSTEM_PROMPT,
    VOICE_RESPONSE_RULES,
    LLMService,
)
from services.models.event_reaction_event import EventReactionEvent
from services.models.game_events import LoadedGameEvent
from services.models.game_state_changed_event import GameStateChangedEvent
from services.models.llm_status import LLMStatus
from services.models.settings_model import (
    ChatCompletionsModel,
    ClaudeAgentSdkModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from services.settings_service import SettingsService


def _make_settings(system_prompt: str = SYSTEM_PROMPT) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(system_prompt=system_prompt, user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


def _make_agent_stream_of(blocks: list):
    """Build a fake execute_query that yields the given blocks and then finishes."""

    async def execute_query(prompt: str):
        for block in blocks:
            yield block

    return execute_query


def _make_failing_agent_stream(error: Exception):
    """Build a fake execute_query that blows up instead of yielding anything."""

    async def execute_query(prompt: str):
        raise error
        yield  # pragma: no cover - only here to keep this an async generator

    return execute_query


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


class LLMServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # LLMService builds the SDK adapter in __init__; patch the class so no
        # real agent (or network call) is created and we can drive execute_query.
        agent_patcher = patch("services.llm_service.ClaudeAgentSDK")
        self.mock_claude_agent_sdk = agent_patcher.start()
        self.addCleanup(agent_patcher.stop)

        # Tool registration reaches for the DI container, which is not wired here.
        register_tools_patcher = patch.object(LLMService, "register_tools")
        self.mock_register_tools = register_tools_patcher.start()
        self.addCleanup(register_tools_patcher.stop)

        self.mock_agent = self.mock_claude_agent_sdk.return_value
        self.mock_agent.execute_query = Mock(
            side_effect=_make_agent_stream_of([AgentText(content="Test output 1")])
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
        # Game state is cached from the last GameStateChangedEvent seen on the bus
        # (see process_game_state_change). Set it directly here so the streaming
        # tests exercise the "state known" path.
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
            self.mock_claude_agent_sdk.call_args.kwargs["system_prompt"],
            f"{VOICE_RESPONSE_RULES}\n{SYSTEM_PROMPT}",
        )
        self.assertIn(
            self.test_game_state,
            self.mock_agent.execute_query.call_args.kwargs["prompt"],
        )

    async def test_should_publish_tts_event_for_every_agent_text(self):
        self.event_bus.publish = AsyncMock()
        self.mock_agent.execute_query = Mock(
            side_effect=_make_agent_stream_of(
                [AgentText(content="First"), AgentText(content="Second")]
            )
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
        self.mock_agent.execute_query.assert_not_called()
        self.assertEqual(self.llm_service.conversation, [])

    async def test_should_report_failed_turn_and_keep_serving_next_message(self):
        # A single broken turn cannot kill the stream - it is the only source of
        # data for COMMS.
        self.mock_agent.execute_query = Mock(
            side_effect=_make_failing_agent_stream(RuntimeError("agent down"))
        )
        self.llm_service.add_llm_request_to_queue("Failing message")

        failed_turn_items = await self._collect_stream_items(3)

        self.assertEqual(failed_turn_items[0], LLMStatus.THINKING)
        self.assertEqual(
            failed_turn_items[1],
            SystemMessage(content="LLM turn failed: agent down"),
        )
        self.assertEqual(failed_turn_items[2], LLMStatus.IDLE)

        self.mock_agent.execute_query = Mock(
            side_effect=_make_agent_stream_of([AgentText(content="Test output 2")])
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

    def test_determine_provider_builds_claude_agent_sdk_from_settings(self):
        settings = _make_settings()
        settings.llm.provider = ClaudeAgentSdkModel(
            type="claude_agent_sdk", model="claude-haiku-4-5-20251001"
        )

        provider = self.llm_service.determine_provider(settings)

        self.assertIs(provider, self.mock_claude_agent_sdk.return_value)
        self.assertEqual(
            self.mock_claude_agent_sdk.call_args.kwargs,
            {
                "model": "claude-haiku-4-5-20251001",
                "system_prompt": f"{VOICE_RESPONSE_RULES}\n{SYSTEM_PROMPT}",
            },
        )

    def test_determine_provider_rejects_chat_completions_provider(self):
        settings = _make_settings()
        settings.llm.provider = ChatCompletionsModel(
            type="chat_completions",
            model="gpt-4",
            base_url="https://example.com",
            bearer_token="token",
        )

        with self.assertRaises(ValueError):
            self.llm_service.determine_provider(settings)

    def test_validate_settings_reports_no_issues(self):
        # The CLI authenticates on its own, so the api key is no longer required.
        settings = _make_settings()

        issue = self.llm_service.validate_settings(settings)

        self.assertIsNone(issue)

    def test_reload_service_rebuilds_agent_with_updated_system_prompt_and_tools(self):
        new_settings = _make_settings(system_prompt="New system prompt")
        self.settings_handler.get_settings.return_value = new_settings

        self.llm_service.reload_service()

        self.assertEqual(
            self.mock_claude_agent_sdk.call_args.kwargs["system_prompt"],
            f"{VOICE_RESPONSE_RULES}\nNew system prompt",
        )
        self.assertEqual(self.mock_register_tools.call_count, 2)


if __name__ == "__main__":
    unittest.main()
