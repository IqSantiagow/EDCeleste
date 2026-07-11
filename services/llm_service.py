import asyncio
from collections.abc import AsyncGenerator
import logging

import anthropic
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langsmith import traceable
from pydantic import SecretStr

from services.event_bus import EventBus
from services.models.keybinds_model import EdAction
from services.models.llm_response import LLMResponse, LLMStatus
from services.tts_service import TTSEvent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are the intelligent space ship pilot assistant called Celeste.
Your job is to assist the human pilot in piloting the ship and managing the
ship's systems. You have access to current state of the game and the
conversation history between you and the human pilot. You have access to
ship systems and you can operate them by performing actions in the game.
"""


class LLMService:
    def __init__(self, api_key: str, event_bus: EventBus) -> None:
        self.conversation: list[BaseMessage] = []
        self.__model = ChatAnthropic(
            model="claude-haiku-4-5-20251001",  # type: ignore
            temperature=0.9,
            max_retries=2,
            api_key=SecretStr(api_key),
        )

        self.__agent = create_agent(
            model=self.__model,
            system_prompt=SYSTEM_PROMPT,
            response_format=LLMResponse,
            tools=self.get_tools(),
        )

        self.__response_queue_watchers: list[asyncio.Queue[LLMResponse]] = []
        self.__status_queue_watchers: list[asyncio.Queue[LLMStatus]] = []
        self.__event_bus = event_bus

    @traceable
    async def send_message(self, message: str, game_state: str):
        logger.info("Got an LLM request: %s", message)
        self.conversation.append(HumanMessage(content=message))

        conv_history_with_state = self.__get_conv_history_with_state(game_state)

        logger.info("Built a conv history : %s", conv_history_with_state)

        for watcher in self.__status_queue_watchers:
            await watcher.put(LLMStatus.THINKING)

        try:
            response = await self.__agent.ainvoke({"messages": conv_history_with_state})  # type: ignore
        finally:
            for watcher in self.__status_queue_watchers:
                await watcher.put(LLMStatus.IDLE)

        validated_response = LLMResponse.model_validate(response["structured_response"])  # type: ignore

        ai_message = validated_response.message.message

        self.conversation.append(AIMessage(content=ai_message))

        for watcher in self.__response_queue_watchers:
            await watcher.put(validated_response)

        await self.__event_bus.publish(TTSEvent(ai_message))

    def get_llm_healthcheck(self) -> bool:
        try:
            self.__model.get_num_tokens_from_messages(
                [HumanMessage(content=SYSTEM_PROMPT)]
            )
            return True
        except anthropic.APIError as e:
            logger.error("LLM health check failed: %s", e)
            return False

    async def stream_responses(self) -> AsyncGenerator[LLMResponse, None]:
        logger.debug("Starting to stream LLM responses")
        watcher_queue: asyncio.Queue[LLMResponse] = asyncio.Queue()
        self.__response_queue_watchers.append(watcher_queue)
        try:
            while True:
                response = await watcher_queue.get()
                yield response
        finally:
            self.__response_queue_watchers.remove(watcher_queue)

    async def stream_llm_status(self) -> AsyncGenerator[LLMStatus, None]:
        logger.debug("Starting to stream LLM status")
        watcher_queue: asyncio.Queue[LLMStatus] = asyncio.Queue()
        self.__status_queue_watchers.append(watcher_queue)
        try:
            while True:
                status = await watcher_queue.get()
                yield status
        finally:
            self.__status_queue_watchers.remove(watcher_queue)

    def __get_conv_history_with_state(self, game_state: str) -> list[BaseMessage]:
        message_history_prompt = self.__merge_conversation_history()

        combined = f"Current game state is: {game_state}\n{message_history_prompt}"

        return [HumanMessage(content=combined)]

    def __merge_conversation_history(self) -> str:
        merged_history = "\n".join(
            [
                f"{'Celeste' if isinstance(msg, AIMessage) else 'Human'}: {msg.content}"
                for msg in self.conversation
            ]
        )
        message_history_prompt = f"""
    This is the conversation history between the pilot and Celeste
                                {merged_history}"""

        return message_history_prompt

    # https://github.com/langchain-ai/langchain/pull/35043
    # https://github.com/LennyMalcolm0/langchain/pull/39
    def get_tools(self):
        @tool("perform_game_action")
        async def perform_action(action: EdAction) -> str:
            """Perform a game action by pressing a key"""
            await self.__event_bus.publish(action)
            logger.info(f"Published action '{action.value}' to event bus")
            return f"Action performed: {action.value}"

        return [perform_action]
