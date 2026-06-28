import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from pydantic import SecretStr

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "You are the intelligent space ship pilot assistant called Celeste."


class LLMService:
    def __init__(self, api_key: str) -> None:
        self.conversation: list[BaseMessage] = []
        self.__model = ChatAnthropic(
            model="claude-haiku-4-5-20251001",  # type: ignore
            temperature=0.9,
            max_retries=2,
            api_key=SecretStr(api_key),
        )

    def send_and_receive_message(self, message: str, game_state: str) -> str:
        logger.debug("Got an LLM request: %s", message)
        self.conversation.append(HumanMessage(content=message))

        conv_history_with_sys_prompt = (
            self.__get_conv_history_with_system_prompt_and_state(game_state)
        )

        logger.debug("Built a conv history : %s", conv_history_with_sys_prompt)

        response = self.__model.invoke(conv_history_with_sys_prompt)
        self.conversation.append(AIMessage(content=response.content))
        return str(response.content)

    def __get_conv_history_with_system_prompt_and_state(
        self, game_state: str
    ) -> list[BaseMessage]:
        # Append sys prompt and state at the beginning of the conv each request
        conv_copy = self.conversation.copy()

        conv_copy.insert(0, SystemMessage(content=SYSTEM_PROMPT, role="system"))

        conv_copy.insert(1, SystemMessage(content=game_state, role="system"))

        return conv_copy
