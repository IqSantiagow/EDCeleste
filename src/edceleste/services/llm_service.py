from collections.abc import AsyncGenerator
from typing import Union
import logging
import asyncio

from edceleste.adapters.claude_agent_sdk import ClaudeAgentSDK
from edceleste.protocols.llm_sdk_protocol import LLMSdkProtocol
from edceleste.services.models.message_block import (
    AgentFullResponse,
    SystemMessage,
    UserMessage,
    AgentText,
    ToolCall,
    ToolResult,
)
from edceleste.protocols.tool_protocol import ToolProtocol
from edceleste.services.event_bus import EventBus
from edceleste.services.models.event_reaction_event import EventReactionEvent
from edceleste.services.models.game_state_changed_event import GameStateChangedEvent
from edceleste.services.models.llm_status import LLMStatus
from edceleste.services.models.llm_stream_item import LLMStreamItem
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.services.tts_service import TTSEvent
from edceleste.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

VOICE_RESPONSE_RULES = """
Every word you write is spoken out loud by a text to speech engine, so you
are talking, not writing. The pilot hears you, he never reads you.

Formatting rules:
- Never use markdown. No asterisks, no hashes, no dashes, no bullet points,
  no numbered lists, no code blocks, no tables, no emoji.
- Write plain spoken sentences. The only punctuation you use is comma,
  period and question mark.
- Never write raw identifiers, file names, coordinates or JSON. Say numbers
  the way a human pilot says them out loud.

Length rules:
- Answer in one or two short sentences, forty words at most.
- Answer only what the pilot asked. Never dump the game state, never list
  ship systems, never report events the pilot did not ask about.
- Never announce what you are about to do and never recap what you just
  did, unless the pilot asked for it.
- No greetings padding, no apologies, no filler like "sure" or "of course".

Address the pilot as Commander.

Example. The pilot says "Hello". You answer "Hello Commander, how can I
assist you today?" and nothing more.
"""

SYSTEM_PROMPT = """
You are the intelligent space ship pilot assistant called Celeste.
Your job is to assist the human pilot in piloting the ship and managing the
ship's systems. You have access to current state of the game and the
conversation history between you and the human pilot. You have access to
ship systems and you can operate them by performing actions in the game.
"""

EVENT_REACTION_PROMPT = """
The game has generated an event that you need to react to. The event is
described below as JSON.
{event_description}
"""


class LLMService:
    def __init__(
        self,
        event_bus: EventBus,
        settings_service: SettingsService,
        tools: list[ToolProtocol],
    ) -> None:
        self.conversation: list[Union[UserMessage, AgentFullResponse]] = []
        self.game_state: str | None = None

        self.__settings_service = settings_service
        self.__event_bus = event_bus

        self.__llm_queue: asyncio.Queue[str] = asyncio.Queue()

        self.__tools = tools

        self.__event_bus.subscribe(EventReactionEvent, self.process_event_reaction)
        self.__event_bus.subscribe(
            GameStateChangedEvent, self.process_game_state_change
        )

        self.reload_service()

    async def __send_message_and_stream_responses(
        self, message: str
    ) -> AsyncGenerator[LLMStreamItem, None]:
        logger.info("Got an LLM request: %s", message)

        if self.game_state is None:
            logger.warning("Game state is not set. Cannot send message to LLM.")

            yield SystemMessage(
                content="Game state is not set. Cannot send message to LLM."
            )

            return

        self.conversation.append(UserMessage(content=message))

        conv_history_with_state = self.__get_conv_history_with_state(self.game_state)

        logger.info("Built a conv history : %s", conv_history_with_state)

        full_response = AgentFullResponse(content="", tool_calls=[], tool_results=[])
        try:
            async for response in self.__agent.execute_query(
                prompt=conv_history_with_state
            ):
                if isinstance(response, AgentText):
                    full_response.content = full_response.content + response.content
                if isinstance(response, ToolCall):
                    full_response.tool_calls.append(response)
                if isinstance(response, ToolResult):
                    full_response.tool_results.append(response)

                yield response

                # Speaking blocks the turn, so the text reaches COMMS first.
                if isinstance(response, AgentText):
                    await self.__event_bus.publish(TTSEvent(response.content))

            self.conversation.append(full_response)

        except Exception as e:
            logger.error("Error while processing LLM response: %s", e)
            # Remove the last user message from the conversation on error
            self.conversation.pop()
            raise e

    def __get_conv_history_with_state(self, game_state: str) -> str:
        message_history_prompt = self.__merge_conversation_history()

        return f"Current game state is: {game_state}\n{message_history_prompt}"

    def __merge_conversation_history(self) -> str:
        merged_history = "\n".join(
            [
                f"{'Celeste' if isinstance(msg, AgentFullResponse) else 'Human'}: "
                f"{msg.content}"
                for msg in self.conversation
            ]
        )
        message_history_prompt = f"""
    This is the conversation history between the pilot and Celeste
                                {merged_history}"""

        return message_history_prompt

    def register_tools(self):
        # TODO: Need to think about how to register tools dynamically
        # to act as extension
        self.__agent.register_tools(self.__tools)

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        if new_settings.llm.provider.type not in ["claude_agent_sdk"]:
            return SettingsIssueModel(
                section="llm",
                field="llm.provider.type",
                message=(
                    "Unsupported LLM provider. "
                    "Supported providers are 'claude_agent_sdk'."
                ),
            )
        return None

    def reload_service(self):
        settings = self.__settings_service.get_settings()

        self.__agent: LLMSdkProtocol = self.determine_provider(settings)
        self.register_tools()

    async def process_event_reaction(self, event: EventReactionEvent) -> None:
        await self.__llm_queue.put(
            EVENT_REACTION_PROMPT.format(
                event_description=event.event.model_dump_json()
            )
        )

    async def process_game_state_change(
        self, game_state: GameStateChangedEvent
    ) -> None:
        self.game_state = game_state.game_state

    def build_system_prompt(self, settings: SettingsModel) -> str:
        """The voice rules are hardcoded in front so a user prompt cannot drop them."""
        user_system_prompt = settings.llm.system_prompt or SYSTEM_PROMPT

        return f"{VOICE_RESPONSE_RULES}\n{user_system_prompt}"

    def determine_provider(self, settings: SettingsModel) -> LLMSdkProtocol:
        provider = settings.llm.provider

        if provider.type == "chat_completions":
            raise ValueError(
                "Chat Completions provider is not supported in this "
                "implementation. Use 'claude_agent_sdk' instead."
            )
        elif provider.type == "claude_agent_sdk":
            return ClaudeAgentSDK(
                model=provider.model,
                system_prompt=self.build_system_prompt(settings),
            )
        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider.type}. Supported providers "
                "are 'claude_agent_sdk'."
            )

    def add_llm_request_to_queue(self, message: str) -> None:
        self.__llm_queue.put_nowait(message)

    async def consume_llm_queue(self) -> AsyncGenerator[LLMStreamItem, None]:
        while True:
            message = await self.__llm_queue.get()

            yield LLMStatus.THINKING

            try:
                async for response in self.__send_message_and_stream_responses(message):
                    yield response
            except Exception as error:
                logger.exception("LLM turn failed")
                yield SystemMessage(content=f"LLM turn failed: {error}")

            yield LLMStatus.IDLE
