from collections.abc import AsyncGenerator
from typing import Union
import logging
import asyncio

from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.message_block import (
    AgentFullResponse,
    SystemMessage,
    UserMessage,
    AgentText,
    Thinking,
    ToolCall,
    ToolResult,
)
from edceleste.protocols.tool_protocol import ToolProtocol
from edceleste.services.event_bus import EventBus
from edceleste.services.models.event_reaction_event import EventReactionEvent
from edceleste.services.models.game_state_changed_event import GameStateChangedEvent
from edceleste.services.models.llm_status import LLMStatus
from edceleste.services.models.llm_stream_item import LLMStreamItem
from edceleste.services.models.settings_model import (
    SUPPORTED_LLM_PROVIDER_TYPES,
    LLMProviderModel,
    SettingsIssueModel,
    SettingsModel,
)
from edceleste.services.tts_service import TTSEvent
from edceleste.services.settings_service import SettingsService
from pydantic_ai import Agent, ModelHTTPError, Tool
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartEndEvent,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import Model, infer_model
from pydantic_ai.providers import Provider, infer_provider_class


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
        """Only stores the dependencies and subscribes to the event bus.

        The agent is not built here. It stays None until reload_service() runs,
        which happens during cold_start() or after the settings change.

        Subscriptions:
        - EventReactionEvent -> queue_reply_to_journal_event
        - GameStateChangedEvent -> remember_latest_game_state
        """
        self.conversation: list[Union[UserMessage, AgentFullResponse]] = []
        self.game_state: str | None = None
        self.__agent: Agent | None = None

        self.__settings_service = settings_service
        self.__event_bus = event_bus

        self.__llm_queue: asyncio.Queue[str] = asyncio.Queue()

        self.__tools = tools

        self.__event_bus.subscribe(
            EventReactionEvent, self.queue_reply_to_journal_event
        )
        self.__event_bus.subscribe(
            GameStateChangedEvent, self.remember_latest_game_state
        )

    async def __stream_reply_speak_it_and_save_to_history(
        self, message: str
    ) -> AsyncGenerator[LLMStreamItem, None]:
        """One full conversation turn for one message from the queue.

        1. No game state yet -> yields a SystemMessage and stops, the LLM is not
           called.
        2. Adds the message to the conversation history as UserMessage.
        3. Sends game state + whole history as one prompt to the agent.
        4. Yields every block (text, tool call, tool result, thinking) to the UI
           and, after yielding, publishes every AgentText as TTSEvent, so Celeste
           says it out loud.
        5. Saves the whole reply as one AgentFullResponse in the history.

        On error the UserMessage from step 2 is removed from the history, so a
        failed turn leaves no half conversation behind, and the error is raised
        again.
        """
        logger.info("Got an LLM request: %s", message)

        if self.game_state is None:
            logger.warning("Game state is not set. Cannot send message to LLM.")

            yield SystemMessage(
                content="Game state is not set. Cannot send message to LLM."
            )

            return

        self.conversation.append(UserMessage(content=message))

        prompt = self.__build_prompt_from_game_state_and_history(self.game_state)

        logger.info("Built a prompt : %s", prompt)

        full_response = AgentFullResponse(content="", tool_calls=[], tool_results=[])
        try:
            async for response in self.stream_agent_response(prompt):
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

    def __build_prompt_from_game_state_and_history(self, game_state: str) -> str:
        """The agent keeps no memory between runs, so every prompt carries the
        current game state first and then the whole conversation history."""
        conversation_history = self.__conversation_history_as_text()

        return f"Current game state is: {game_state}\n{conversation_history}"

    def __conversation_history_as_text(self) -> str:
        """One line per message: "Human: ..." for the pilot and "Celeste: ..."
        for the agent. Only the text goes in, tool calls and results are left
        out."""
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

    async def stream_agent_response(
        self, prompt: str
    ) -> AsyncGenerator[AgentText | ToolCall | ToolResult | Thinking, None]:
        """Runs the agent once and yields only the blocks the app shows.

        The agent may call tools in between. pydantic_ai runs them by itself
        and they come back here as ToolCall and ToolResult blocks.
        Raises RuntimeError when reload_service() has not built the agent yet.
        Does not touch the history and does not speak, the caller does that.
        """
        if self.__agent is None:
            raise RuntimeError(
                "LLM is not configured. Check the LLM settings and restart."
            )

        async with self.__agent.run_stream_events(prompt) as events:
            async for event in events:
                block = self.to_message_block(event)

                if block is not None:
                    yield block

    def to_message_block(
        self, event: object
    ) -> AgentText | ToolCall | ToolResult | Thinking | None:
        """Turns one pydantic_ai stream event into one app block.

        - PartEndEvent with TextPart -> AgentText
        - PartEndEvent with ThinkingPart -> Thinking
        - FunctionToolCallEvent -> ToolCall
        - FunctionToolResultEvent -> ToolResult
        - anything else, e.g. the text deltas -> None, the caller skips it
        """
        # A part is only complete on PartEndEvent, speaking every delta would
        # cut the sentence into pieces.
        if isinstance(event, PartEndEvent):
            if isinstance(event.part, TextPart):
                return AgentText(content=event.part.content)
            if isinstance(event.part, ThinkingPart):
                return Thinking(content=event.part.content)
        if isinstance(event, FunctionToolCallEvent):
            return self.to_tool_call(event.part)
        if isinstance(event, FunctionToolResultEvent):
            return self.to_tool_result(event.part)

        return None

    def to_tool_call(self, part: ToolCallPart) -> ToolCall:
        """Adds the readable name and the parameter name of our tool, so the UI
        can show "Perform Game Action" instead of "perform_game_action".
        When the LLM calls a tool we do not have, the raw tool name is used and
        param_name is None."""
        tool = self.find_tool(part.tool_name)

        return ToolCall(
            tool_name=part.tool_name,
            input=part.args_as_dict(),
            tool_readable_name=tool.readable_name if tool else part.tool_name,
            param_name=tool.param_name if tool else None,
        )

    def to_tool_result(self, part: ToolReturnPart | RetryPromptPart) -> ToolResult:
        """RetryPromptPart means pydantic_ai rejected the tool call (bad
        arguments, unknown tool) and asks the LLM to try again, so it is shown
        as an error. A normal ToolReturnPart is an error only when the tool put
        "is_error" in its metadata."""
        if isinstance(part, RetryPromptPart):
            return ToolResult(content=part.model_response(), is_error=True)

        metadata = part.metadata or {}

        return ToolResult(
            content=part.content,  # type: ignore
            is_error=bool(metadata.get("is_error")),
        )

    def build_tools(self) -> list[Tool]:
        """Wraps every tool's execute method in pydantic_ai.Tool. pydantic_ai
        reads the arguments from the execute signature and the description from
        its docstring, so no tool writes a JSON schema by hand."""
        return [Tool(tool.execute, name=tool.name) for tool in self.__tools]

    def find_tool(self, tool_name: str) -> ToolProtocol | None:
        """Returns None when the LLM asked for a tool name we do not have."""
        return next((tool for tool in self.__tools if tool.name == tool_name), None)

    async def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Checks the LLM part of new settings before they are saved. Goes to
        the network.

        Checks in order and returns the first issue:
        1. provider type is in SUPPORTED_LLM_PROVIDER_TYPES,
        2. the provider can be reached (only fails when building the provider
           raises, network errors of the model list end as an empty list),
        3. the model is on the provider's model list. An empty list means "we
           could not check", so every model passes.
        Returns None when everything is fine.
        """
        if new_settings.llm.provider.type not in SUPPORTED_LLM_PROVIDER_TYPES:
            return SettingsIssueModel(
                section="llm",
                field="llm.provider.type",
                message=(
                    "Unsupported LLM provider. Supported providers are "
                    f"{', '.join(SUPPORTED_LLM_PROVIDER_TYPES)}."
                ),
            )
        try:
            available_models = await self.fetch_available_model_names(
                new_settings.llm.provider
            )
        except Exception as error:
            return SettingsIssueModel(
                section="llm",
                field="llm.provider.type",
                message=f"Cannot reach the LLM provider: {error}",
            )

        if available_models and new_settings.llm.provider.model not in available_models:
            return SettingsIssueModel(
                section="llm",
                field="llm.provider.model",
                message=(
                    "Unsupported LLM model. Supported models are "
                    f"{', '.join(available_models)}."
                ),
            )

        return None

    def reload_service(self):
        """Builds a new agent from the current settings: model, system prompt
        and tools. The conversation history, the game state and the queue stay
        as they are. Does not go to the network, a wrong API key shows up only
        on the first request or in find_connection_error()."""
        settings = self.__settings_service.get_settings()

        self.model = self.build_model(settings.llm.provider)

        self.__agent = Agent(
            model=self.model,
            system_prompt=self.build_system_prompt(settings),
            tools=self.build_tools(),
        )

    async def queue_reply_to_journal_event(self, event: EventReactionEvent) -> None:
        """Puts a prompt with the journal event as JSON into the LLM queue.
        It does not decide if the event deserves a reply, EventReactionsService
        already did that before publishing. The reply comes later from
        consume_llm_queue(), like any message typed by the pilot."""
        await self.__llm_queue.put(
            EVENT_REACTION_PROMPT.format(
                event_description=event.event.model_dump_json()
            )
        )

    async def remember_latest_game_state(
        self, game_state_changed_event: GameStateChangedEvent
    ) -> None:
        """Only stores the newest game state text for the next prompt. Does not
        call the LLM."""
        self.game_state = game_state_changed_event.game_state

    def build_system_prompt(self, settings: SettingsModel) -> str:
        """VOICE_RESPONSE_RULES always go first, so a user system prompt cannot
        drop them. Without a user system prompt the built in SYSTEM_PROMPT is
        used."""
        user_system_prompt = settings.llm.system_prompt or SYSTEM_PROMPT

        return f"{VOICE_RESPONSE_RULES}\n{user_system_prompt}"

    def build_provider(self, provider_settings: LLMProviderModel) -> Provider:
        """Lets pydantic_ai pick the provider class from the type name, so every
        provider it supports works from config alone. base_url is passed only
        when set (ollama, vllm, azure). Raises ValueError for a type we do not
        support."""
        if provider_settings.type not in SUPPORTED_LLM_PROVIDER_TYPES:
            raise ValueError(
                f"Unsupported LLM provider: {provider_settings.type}. Supported "
                f"providers are {', '.join(SUPPORTED_LLM_PROVIDER_TYPES)}."
            )

        provider_class = infer_provider_class(provider_settings.type)

        if provider_settings.base_url:
            return provider_class(
                api_key=provider_settings.api_key,
                base_url=provider_settings.base_url,
            )  # type: ignore

        return provider_class(api_key=provider_settings.api_key)  # type: ignore

    def build_model(self, provider_settings: LLMProviderModel) -> Model:
        """pydantic_ai names a model "provider:model", our config keeps the two
        apart, so they are joined here. The provider comes from
        build_provider(), so the API key and base_url are used."""
        return infer_model(
            f"{provider_settings.type}:{provider_settings.model}",
            provider_factory=lambda _: self.build_provider(provider_settings),
        )

    def add_llm_request_to_queue(self, message: str) -> None:
        """Does not wait for the reply. The reply comes out of
        consume_llm_queue()."""
        self.__llm_queue.put_nowait(message)

    async def consume_llm_queue(self) -> AsyncGenerator[LLMStreamItem, None]:
        """Never ends. Takes messages from the queue one by one, so two
        requests never talk to the LLM at the same time.

        For every message it yields:
        1. LLMStatus.THINKING,
        2. every block of the reply,
        3. LLMStatus.IDLE.
        A failed turn does not stop the loop, the error is yielded as a
        SystemMessage and the next message is taken.
        """
        while True:
            message = await self.__llm_queue.get()

            yield LLMStatus.THINKING

            try:
                async for response in self.__stream_reply_speak_it_and_save_to_history(
                    message
                ):
                    yield response
            except Exception as error:
                logger.exception(f"LLM turn failed: {error}", exc_info=error)
                yield SystemMessage(content=f"LLM turn failed: {error}")

            yield LLMStatus.IDLE

    async def fetch_available_model_names(
        self, provider_settings: LLMProviderModel | None = None
    ) -> list[str]:
        """Asks the provider for its model list over the network. Without
        provider_settings the provider from the saved settings is used.

        Returns an empty list when the provider client has no model list
        or when the request fails. An empty list means "we
        do not know", not "no models"."""
        provider_settings = (
            provider_settings or self.__settings_service.get_settings().llm.provider
        )
        built_provider = self.build_provider(provider_settings)

        client = getattr(built_provider, "client", None)
        if not hasattr(client, "models"):
            return []

        try:
            # Google is not async, so we just catch it in
            # exception and return list anyway.

            models = await client.models.list()  # type: ignore
        except Exception as e:
            logger.exception(f"Failed to fetch models: {e}", exc_info=e)
            return []

        return [model.id for model in models.data]

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Builds the agent (reload_service) and sends one real test request
           (find_connection_error), which costs a few tokens.
        3. Yields the status again with completed=True and the error text in
           message, or message=None when the LLM answered.
        Never raises, every error ends up in the status message.
        """
        status = ColdStartStatus(
            service="llm",
            message=None,
            is_critical=False,
            completed=False,
        )
        yield status

        try:
            self.reload_service()
            # Same check as the Test connection button in settings.
            provider_settings = self.__settings_service.get_settings().llm.provider
            status.message = await self.find_connection_error(provider_settings)
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status

    async def find_connection_error(
        self, provider_settings: LLMProviderModel
    ) -> str | None:
        """Sends "Respond with only 'OK'" to a fresh agent built from
        provider_settings, not from the saved settings, so the settings screen
        can test values before saving them.

        Returns None when the LLM answered within 15 s. Otherwise returns a
        short error text for the UI:
        - "No answer within 15 s" on timeout,
        - "HTTP <code>: <provider message>" plus a suggested model, if the
          provider sent one,
        - the exception text for anything else.
        The API key is replaced with "[REDACTED API KEY]" and the text is cut to
        200 characters, because it is shown on the screen.
        """
        MAX_REASON = 200
        try:
            model = self.build_model(provider_settings)

            await asyncio.wait_for(
                Agent(model=model).run("Respond with only 'OK'"), timeout=15
            )
            return None
        except TimeoutError:
            return "No answer within 15 s"
        except ModelHTTPError as e:
            reason = f"HTTP {e.status_code}"
            if message := self._extract_error_message_from_provider_response(e.body):
                reason += f": {message}"
            error_message = reason
            if e.suggested_model_id:
                error_message += f" Did you mean to use: {e.suggested_model_id} ?"

        except Exception as e:
            error_message = str(e)

        if provider_settings.api_key:
            # If there is any chance the API key appears in the error message,
            # redact it.
            error_message = error_message.replace(
                provider_settings.api_key, "[REDACTED API KEY]"
            )

        error_message = error_message[:MAX_REASON]

        return error_message

    @staticmethod
    def _extract_error_message_from_provider_response(
        response_body: object,
    ) -> str | None:
        """Providers put the error text in different places. Looks for
        {"message": "..."} first, then {"error": {"message": "..."}}.
        Returns None when the body is not a dict or has neither."""
        if not isinstance(response_body, dict):
            return None
        error = response_body.get("error")
        nested = error.get("message") if isinstance(error, dict) else None
        return response_body.get("message") or nested
