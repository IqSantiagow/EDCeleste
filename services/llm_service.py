import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import SecretStr

from projection.game_state import GameState

logger = logging.getLogger(__name__)

# ONLY FOR TESTING

SYSTEM_PROMPT = "Your are the intelligent space ship pilot assistant called Celeste."

class LLMService:

    def __init__(self, game_state: GameState, api_key: str) -> None:
        self.game_state: GameState = game_state
        self.conversation: list[Any] = []
        self.__model = ChatAnthropic(  # type: ignore[call-arg]
        model="claude-haiku-4-5",
        temperature=0.9,
        max_retries=2,
        api_key=SecretStr(api_key)
    )

    def send_and_receive_message(self, message: str) -> str:
        logger.debug("Got an LLM request: %s", message)
        self.conversation.append(HumanMessage(content=message))

        conv_history_with_sys_prompt = self.__get_conv_history_with_system_prompt_and_state()

        logger.debug("Built a conv history : %s", conv_history_with_sys_prompt)

        response = self.__model.invoke(conv_history_with_sys_prompt)
        self.conversation.append(AIMessage(content=response.content))
        return str(response.content)

    def __get_conv_history_with_system_prompt_and_state(self) -> list[Any]:
        # Append sys prompt and state at the beginning of the conv each request
        game_state = self.game_state.get_game_state_projection()
        conv_copy = self.conversation.copy()

        conv_copy.insert(0, SystemMessage(content=SYSTEM_PROMPT, role="system"))

        conv_copy.insert(0, SystemMessage(content=game_state, role="system"))

        return conv_copy
